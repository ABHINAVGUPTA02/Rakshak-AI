"""Sync PostgreSQL crime records to Neo4j knowledge graph."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, joinedload

from app.db.neo4j import neo4j_session
from app.models.crime import CrimeRecord
from app.services.ingestion.fir_parser import ensure_crime_persons

logger = logging.getLogger(__name__)

GRAPH_LABELS = ("Crime", "Person", "Location", "PoliceStation", "CrimeType")


def _is_missing(value: str | None) -> bool:
    if not value:
        return True
    return value.strip().lower() in {"unknown", "na", "n/a", "nil", "none", ""}


def _node_id(node) -> str:
    label = list(node.labels)[0]
    props = dict(node)
    if label == "Crime":
        return f"crime:{props.get('fir_number', '')}"
    if label == "Person":
        return f"person:{props.get('name', '')}:{props.get('role', '')}"
    if label in ("Location", "PoliceStation", "CrimeType"):
        return f"{label.lower()}:{props.get('name', '')}"
    return f"{label.lower()}:{props.get('name') or props.get('fir_number') or props.get('id', '')}"


def _node_label(node) -> str:
    label = list(node.labels)[0]
    props = dict(node)
    if label == "Crime":
        return props.get("fir_number") or "Crime"
    if label == "Person":
        role = props.get("role", "")
        name = props.get("name") or "Person"
        return f"{name} ({role})" if role else name
    return props.get("name") or props.get("fir_number") or label


def sync_crime_to_graph(db: Session, crime_id: int) -> bool:
    crime = (
        db.query(CrimeRecord)
        .options(joinedload(CrimeRecord.persons))
        .filter(CrimeRecord.id == crime_id)
        .first()
    )
    if not crime:
        return False

    crime = ensure_crime_persons(db, crime)
    # Re-load with persons after backfill commit
    crime = (
        db.query(CrimeRecord)
        .options(joinedload(CrimeRecord.persons))
        .filter(CrimeRecord.id == crime_id)
        .first()
    )
    if not crime:
        return False

    persons_payload = [
        {
            "name": person.name,
            "role": person.role.value,
            "age": person.age,
            "address": person.address or "",
        }
        for person in crime.persons
    ]

    district = crime.district.strip() if crime.district else ""
    police_station = crime.police_station.strip() if crime.police_station else ""
    crime_type = crime.crime_type.strip() if crime.crime_type else "Unknown"

    try:
        with neo4j_session() as session:
            # Core crime + typed entities and district / station / classification links
            session.run(
                """
                MERGE (c:Crime {fir_number: $fir_number})
                SET c.crime_type = $crime_type,
                    c.district = $district,
                    c.status = $status,
                    c.description = $description,
                    c.incident_date = $incident_date,
                    c.police_station = $police_station

                MERGE (ct:CrimeType {name: $crime_type})
                MERGE (c)-[:CLASSIFIED_AS]->(ct)

                FOREACH (_ IN CASE WHEN $has_district THEN [1] ELSE [] END |
                    MERGE (l:Location {name: $district})
                    SET l.kind = 'district'
                    MERGE (c)-[:OCCURRED_IN]->(l)
                    MERGE (ct)-[:OCCURS_IN]->(l)
                )

                FOREACH (_ IN CASE WHEN $has_police_station THEN [1] ELSE [] END |
                    MERGE (ps:PoliceStation {name: $police_station})
                    MERGE (c)-[:FILED_AT]->(ps)
                    FOREACH (__ IN CASE WHEN $has_district THEN [1] ELSE [] END |
                        MERGE (l2:Location {name: $district})
                        MERGE (ps)-[:IN_DISTRICT]->(l2)
                    )
                )
                """,
                fir_number=crime.fir_number,
                crime_type=crime_type,
                district=district,
                has_district=not _is_missing(district),
                police_station=police_station,
                has_police_station=not _is_missing(police_station),
                status=crime.status,
                description=crime.description or "",
                incident_date=crime.incident_date.isoformat() if crime.incident_date else None,
            )

            if persons_payload:
                session.run(
                    """
                    MATCH (c:Crime {fir_number: $fir_number})
                    UNWIND $persons AS person
                    MERGE (p:Person {name: person.name, role: person.role})
                    SET p.age = person.age,
                        p.address = person.address
                    MERGE (p)-[rel:INVOLVED_IN]->(c)
                    SET rel.role = person.role
                    WITH p, person
                    MATCH (ct:CrimeType {name: $crime_type})
                    MERGE (p)-[:LINKED_TO_TYPE {role: person.role}]->(ct)
                    """,
                    fir_number=crime.fir_number,
                    crime_type=crime_type,
                    persons=persons_payload,
                )

                # Co-involved persons in the same FIR
                if len(persons_payload) > 1:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})<-[:INVOLVED_IN]-(p1:Person)
                        MATCH (c)<-[:INVOLVED_IN]-(p2:Person)
                        WHERE p1.name < p2.name
                        MERGE (p1)-[:CO_INVOLVED]->(p2)
                        """,
                        fir_number=crime.fir_number,
                    )

            # Repeat offenders / victims: same person name+role across multiple crimes
            for person in persons_payload:
                session.run(
                    """
                    MATCH (p:Person {name: $name, role: $role})-[:INVOLVED_IN]->(other:Crime)
                    WHERE other.fir_number <> $fir_number
                    WITH p, collect(DISTINCT other) AS others
                    WHERE size(others) > 0
                    MATCH (p)-[:INVOLVED_IN]->(c:Crime {fir_number: $fir_number})
                    UNWIND others AS linked
                    MERGE (c)-[:RELATED_TO {via: $name}]->(linked)
                    """,
                    name=person["name"],
                    role=person["role"],
                    fir_number=crime.fir_number,
                )

        return True
    except Exception as exc:
        logger.warning("Neo4j sync failed for crime %s: %s", crime.fir_number, exc)
        return False


def sync_all_crimes(db: Session) -> int:
    crimes = db.query(CrimeRecord).options(joinedload(CrimeRecord.persons)).all()
    synced = 0
    for crime in crimes:
        if sync_crime_to_graph(db, crime.id):
            synced += 1
    return synced


def get_network_graph(limit: int = 500) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node) -> None:
        if node is None:
            return
        node_key = _node_id(node)
        label_type = list(node.labels)[0].lower()
        nodes[node_key] = {
            "id": node_key,
            "label": _node_label(node),
            "type": label_type,
        }

    def add_edge(source_node, rel, target_node) -> None:
        if source_node is None or target_node is None or rel is None:
            return
        source = _node_id(source_node)
        target = _node_id(target_node)
        rel_type = rel.type
        edge_key = (source, target, rel_type)
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        add_node(source_node)
        add_node(target_node)
        edges.append({"source": source, "target": target, "relationship": rel_type})

    label_filter = list(GRAPH_LABELS)

    try:
        with neo4j_session() as session:
            # All directed relationships between graph entity types
            rel_result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE any(l IN labels(a) WHERE l IN $labels)
                  AND any(l IN labels(b) WHERE l IN $labels)
                RETURN a, r, b
                LIMIT $limit
                """,
                labels=label_filter,
                limit=limit,
            )
            for record in rel_result:
                add_edge(record["a"], record["r"], record["b"])

            # Orphan nodes (no edges yet)
            orphan_result = session.run(
                """
                MATCH (n)
                WHERE any(l IN labels(n) WHERE l IN $labels)
                  AND NOT (n)-[]-()
                RETURN n
                LIMIT 100
                """,
                labels=label_filter,
            )
            for record in orphan_result:
                add_node(record["n"])

    except Exception as exc:
        logger.warning("Failed to fetch network graph: %s", exc)
        return {"nodes": [], "edges": []}

    return {"nodes": list(nodes.values()), "edges": edges}
