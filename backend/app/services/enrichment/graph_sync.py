import logging

from sqlalchemy.orm import Session

from app.db.neo4j import neo4j_session
from app.models.crime import CrimeRecord, Person

logger = logging.getLogger(__name__)


def sync_crime_to_graph(db: Session, crime_id: int) -> bool:
    crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
    if not crime:
        return False

    try:
        with neo4j_session() as session:
            session.run(
                """
                MERGE (c:Crime {fir_number: $fir_number})
                SET c.crime_type = $crime_type,
                    c.district = $district,
                    c.status = $status,
                    c.description = $description
                MERGE (l:Location {name: $district})
                MERGE (c)-[:OCCURRED_IN]->(l)
                """,
                fir_number=crime.fir_number,
                crime_type=crime.crime_type,
                district=crime.district,
                status=crime.status,
                description=crime.description or "",
            )

            for person in crime.persons:
                session.run(
                    """
                    MERGE (p:Person {name: $name, role: $role})
                    SET p.age = $age
                    WITH p
                    MATCH (c:Crime {fir_number: $fir_number})
                    MERGE (p)-[:INVOLVED_IN {role: $role}]->(c)
                    """,
                    name=person.name,
                    role=person.role.value,
                    age=person.age,
                    fir_number=crime.fir_number,
                )
        return True
    except Exception as exc:
        logger.warning("Neo4j sync failed for crime %s: %s", crime.fir_number, exc)
        return False


def sync_all_crimes(db: Session) -> int:
    crimes = db.query(CrimeRecord).all()
    for crime in crimes:
        sync_crime_to_graph(db, crime.id)
    return len(crimes)


def get_network_graph(limit: int = 50) -> dict:
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (a)-[r]->(b)
            RETURN a, r, b
            LIMIT $limit
            """
        , limit=limit)
        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        for record in result:
            for key in ("a", "b"):
                node = record[key]
                node_id = f"{list(node.labels)[0]}:{node.get('name') or node.get('fir_number')}"
                nodes[node_id] = {
                    "id": node_id,
                    "label": node.get("name") or node.get("fir_number") or node_id,
                    "type": list(node.labels)[0].lower(),
                }
            rel = record["r"]
            source = f"{list(record['a'].labels)[0]}:{record['a'].get('name') or record['a'].get('fir_number')}"
            target = f"{list(record['b'].labels)[0]}:{record['b'].get('name') or record['b'].get('fir_number')}"
            edges.append({"source": source, "target": target, "relationship": rel.type})

        return {"nodes": list(nodes.values()), "edges": edges}
