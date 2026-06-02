"""Sync PostgreSQL crime records to Neo4j — investigation-focused knowledge graph."""

from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy.orm import Session, joinedload

from app.db.neo4j import neo4j_session
import app.models.operational  # noqa: F401 — register CrimeRecord.transactions / call_logs
from app.models.crime import CrimeRecord
from app.services.ingestion.fir_parser import ensure_crime_entities, ensure_crime_persons

logger = logging.getLogger(__name__)

# Node labels stored in Neo4j
GRAPH_LABELS = (
    "Crime",
    "Person",
    "Phone",
    "Email",
    "Vehicle",
    "Account",
    "Property",
    "Document",
    "Transaction",
    "Call",
)

# Default API view — hide structural / duplicate clutter
SKIP_NODE_TYPES = frozenset({"crimetype", "location", "policestation"})

INVESTIGATION_RELATIONSHIPS = frozenset(
    {
        "INVOLVED_IN",
        "CO_SUSPECT",
        "USES_PHONE",
        "USES_EMAIL",
        "INVOLVES_VEHICLE",
        "FINANCIAL_LINK",
        "INVOLVES_PROPERTY",
        "USES_DOCUMENT",
        "HAS_PHONE",
        "HAS_EMAIL",
        "HAS_DOCUMENT",
        "HAS_TRANSACTION",
        "PAID_FROM",
        "PAID_TO",
        "CALL_RECORD",
        "CALLER",
        "RECEIVER",
    }
)

RELATIONSHIP_LABELS: dict[str, str] = {
    "INVOLVED_IN": "involved in",
    "CO_SUSPECT": "co-suspect",
    "USES_PHONE": "phone in case",
    "USES_EMAIL": "email in case",
    "INVOLVES_VEHICLE": "vehicle",
    "FINANCIAL_LINK": "bank account",
    "INVOLVES_PROPERTY": "property",
    "USES_DOCUMENT": "document",
    "HAS_PHONE": "has phone",
    "HAS_EMAIL": "has email",
    "HAS_DOCUMENT": "has document",
    "HAS_TRANSACTION": "transaction",
    "PAID_FROM": "paid from",
    "PAID_TO": "paid to",
    "CALL_RECORD": "call log",
    "CALLER": "caller",
    "RECEIVER": "receiver",
}

KIND_TO_LABEL = {
    "phone": "Phone",
    "email": "Email",
    "vehicle": "Vehicle",
    "account": "Account",
    "property": "Property",
    "document": "Document",
}


def _is_missing(value: str | None) -> bool:
    if not value:
        return True
    return value.strip().lower() in {"unknown", "na", "n/a", "nil", "none", ""}


def _slug(value: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip())[:max_len]
    return slug or hashlib.md5(value.encode()).hexdigest()[:12]


def clear_graph() -> None:
    with neo4j_session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def _node_id(node) -> str:
    label = list(node.labels)[0]
    props = dict(node)
    if label == "Crime":
        return f"crime:{props.get('fir_number', '')}"
    if label == "Person":
        return f"person:{props.get('name', '')}"
    if label in ("Phone", "Email", "Vehicle", "Account", "Document", "Transaction", "Call"):
        return f"{label.lower()}:{props.get('value', props.get('id', ''))}"
    if label == "Property":
        return f"property:{props.get('value_id', props.get('value', ''))}"
    return f"{label.lower()}:{props.get('name') or props.get('value') or ''}"


def _node_label(node) -> str:
    label = list(node.labels)[0]
    props = dict(node)
    if label == "Crime":
        ctype = props.get("crime_type") or ""
        fir = props.get("fir_number") or "Case"
        if ctype and ctype.lower() != "unknown":
            return f"{fir}\n{ctype}"
        return fir
    if label == "Person":
        name = props.get("name") or "Person"
        return name
    if label == "Phone":
        return props.get("value") or "Phone"
    if label == "Account":
        val = props.get("value") or "Account"
        return val if len(val) <= 14 else val[:12] + "…"
    if label == "Transaction":
        amount = props.get("amount")
        if amount is not None:
            return f"₹{amount:,.0f}" if amount >= 1000 else f"₹{amount:.0f}"
        return "Txn"
    if label == "Call":
        return props.get("label") or "Call"
    if label in ("Email", "Vehicle", "Document", "Property"):
        display = props.get("label") or props.get("value") or label
        text = str(display)
        return text[:18] + "…" if len(text) > 18 else text
    return props.get("name") or props.get("value") or label


def _node_meta(node) -> dict[str, str | None]:
    label = list(node.labels)[0]
    props = dict(node)
    meta: dict[str, str | None] = {"kind": label.lower()}
    if label == "Crime":
        meta["fir_number"] = props.get("fir_number")
        meta["crime_type"] = props.get("crime_type")
        meta["district"] = props.get("district")
    if label == "Person":
        meta["name"] = props.get("name")
    if label == "Phone":
        meta["value"] = props.get("value")
    return meta


def _edge_label(rel_type: str, rel_props: dict | None) -> str:
    if rel_type == "INVOLVED_IN" and rel_props:
        role = rel_props.get("role")
        if role:
            return str(role)
    return RELATIONSHIP_LABELS.get(rel_type, rel_type.replace("_", " ").lower())


def _entity_relationship(kind: str) -> str:
    return {
        "phone": "USES_PHONE",
        "email": "USES_EMAIL",
        "vehicle": "INVOLVES_VEHICLE",
        "account": "FINANCIAL_LINK",
        "property": "INVOLVES_PROPERTY",
        "document": "USES_DOCUMENT",
    }.get(kind, "USES_PHONE")


def sync_crime_to_graph(db: Session, crime_id: int) -> bool:
    crime = (
        db.query(CrimeRecord)
        .options(
            joinedload(CrimeRecord.persons),
            joinedload(CrimeRecord.entities),
            joinedload(CrimeRecord.transactions),
            joinedload(CrimeRecord.call_logs),
        )
        .filter(CrimeRecord.id == crime_id)
        .first()
    )
    if not crime:
        return False

    crime = ensure_crime_persons(db, crime)
    crime = ensure_crime_entities(db, crime)

    crime = (
        db.query(CrimeRecord)
        .options(
            joinedload(CrimeRecord.persons),
            joinedload(CrimeRecord.entities),
            joinedload(CrimeRecord.transactions),
            joinedload(CrimeRecord.call_logs),
        )
        .filter(CrimeRecord.id == crime_id)
        .first()
    )
    if not crime:
        return False

    district = crime.district.strip() if crime.district else ""
    police_station = crime.police_station.strip() if crime.police_station else ""
    crime_type = crime.crime_type.strip() if crime.crime_type else "Unknown"

    try:
        with neo4j_session() as session:
            # Replace prior edges for this case (keeps shared Person/Phone nodes)
            session.run(
                """
                MATCH (c:Crime {fir_number: $fir_number})-[r]-()
                DELETE r
                """,
                fir_number=crime.fir_number,
            )

            session.run(
                """
                MERGE (c:Crime {fir_number: $fir_number})
                SET c.crime_type = $crime_type,
                    c.district = $district,
                    c.police_station = $police_station,
                    c.status = $status,
                    c.description = $description,
                    c.incident_date = $incident_date
                """,
                fir_number=crime.fir_number,
                crime_type=crime_type,
                district=district if not _is_missing(district) else "",
                police_station=police_station if not _is_missing(police_station) else "",
                status=crime.status,
                description=(crime.description or "")[:2000],
                incident_date=crime.incident_date.isoformat() if crime.incident_date else None,
            )

            persons_payload = [
                {
                    "name": person.name,
                    "role": person.role.value,
                    "age": person.age,
                    "address": person.address or "",
                }
                for person in crime.persons
            ]

            if persons_payload:
                session.run(
                    """
                    MATCH (c:Crime {fir_number: $fir_number})
                    UNWIND $persons AS person
                    MERGE (p:Person {name: person.name})
                    SET p.age = coalesce(person.age, p.age),
                        p.address = CASE WHEN person.address <> '' THEN person.address ELSE p.address END
                    MERGE (p)-[rel:INVOLVED_IN]->(c)
                    SET rel.role = person.role
                    """,
                    fir_number=crime.fir_number,
                    persons=persons_payload,
                )

                session.run(
                    """
                    MATCH (c:Crime {fir_number: $fir_number})<-[r1:INVOLVED_IN {role: 'accused'}]-(p1:Person)
                    MATCH (c)<-[r2:INVOLVED_IN {role: 'accused'}]-(p2:Person)
                    WHERE p1.name < p2.name
                    MERGE (p1)-[:CO_SUSPECT]->(p2)
                    """,
                    fir_number=crime.fir_number,
                )

            for ent in crime.entities:
                kind = ent.kind.value
                label = KIND_TO_LABEL.get(kind)
                rel = _entity_relationship(kind)
                if not label:
                    continue

                value_id = _slug(ent.value)
                if kind == "property":
                    session.run(
                        f"""
                        MATCH (c:Crime {{fir_number: $fir_number}})
                        MERGE (n:Property {{value_id: $value_id}})
                        SET n.value = $value, n.label = $label
                        MERGE (c)-[:{rel}]->(n)
                        """,
                        fir_number=crime.fir_number,
                        value_id=value_id,
                        value=ent.value,
                        label=ent.label or ent.value,
                    )
                    entity_match = "n:Property {value_id: $value_key}"
                    value_key = value_id
                else:
                    session.run(
                        f"""
                        MATCH (c:Crime {{fir_number: $fir_number}})
                        MERGE (n:{label} {{value: $value}})
                        SET n.label = $label
                        MERGE (c)-[:{rel}]->(n)
                        """,
                        fir_number=crime.fir_number,
                        value=ent.value,
                        label=ent.label or ent.value,
                    )
                    entity_match = f"n:{label} {{value: $value_key}}"
                    value_key = ent.value

                if ent.role:
                    person_rel = {"phone": "HAS_PHONE", "email": "HAS_EMAIL", "document": "HAS_DOCUMENT"}.get(kind)
                    if person_rel:
                        session.run(
                            f"""
                            MATCH (c:Crime {{fir_number: $fir_number}})<-[inv:INVOLVED_IN]-(p:Person)
                            WHERE inv.role = $role
                            MATCH ({entity_match})
                            MERGE (p)-[:{person_rel}]->(n)
                            """,
                            fir_number=crime.fir_number,
                            role=ent.role,
                            value_key=value_key,
                        )

            for txn in crime.transactions:
                txn_id = f"TXN_{txn.id}"
                session.run(
                    """
                    MATCH (c:Crime {fir_number: $fir_number})
                    MERGE (t:Transaction {value: $txn_id})
                    SET t.amount = $amount,
                        t.currency = $currency,
                        t.label = $label,
                        t.txn_type = $txn_type,
                        t.txn_date = $txn_date
                    MERGE (c)-[:HAS_TRANSACTION]->(t)
                    """,
                    fir_number=crime.fir_number,
                    txn_id=txn_id,
                    amount=txn.amount,
                    currency=txn.currency or "INR",
                    label=txn.description or (f"₹{txn.amount}" if txn.amount else "Transaction"),
                    txn_type=txn.transaction_type or "",
                    txn_date=txn.transaction_date.isoformat() if txn.transaction_date else None,
                )
                if txn.from_account:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})-[:HAS_TRANSACTION]->(t:Transaction {value: $txn_id})
                        MERGE (a:Account {value: $value})
                        MERGE (t)-[:PAID_FROM]->(a)
                        MERGE (c)-[:FINANCIAL_LINK]->(a)
                        """,
                        fir_number=crime.fir_number,
                        txn_id=txn_id,
                        value=txn.from_account,
                    )
                if txn.to_account:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})-[:HAS_TRANSACTION]->(t:Transaction {value: $txn_id})
                        MERGE (a:Account {value: $value})
                        MERGE (t)-[:PAID_TO]->(a)
                        MERGE (c)-[:FINANCIAL_LINK]->(a)
                        """,
                        fir_number=crime.fir_number,
                        txn_id=txn_id,
                        value=txn.to_account,
                    )
                if txn.upi_id:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})
                        MERGE (a:Account {value: $value})
                        SET a.label = 'UPI'
                        MERGE (c)-[:FINANCIAL_LINK]->(a)
                        """,
                        fir_number=crime.fir_number,
                        value=txn.upi_id,
                    )

            for call in crime.call_logs:
                call_id = f"CALL_{call.id}"
                caller = call.caller_phone
                callee = call.callee_phone
                session.run(
                    """
                    MATCH (c:Crime {fir_number: $fir_number})
                    MERGE (cl:Call {value: $call_id})
                    SET cl.label = $label,
                        cl.duration = $duration,
                        cl.call_date = $call_date
                    MERGE (c)-[:CALL_RECORD]->(cl)
                    """,
                    fir_number=crime.fir_number,
                    call_id=call_id,
                    label=f"{caller or '?'} → {callee or '?'}",
                    duration=call.duration_seconds,
                    call_date=call.call_date.isoformat() if call.call_date else None,
                )
                if caller:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})-[:CALL_RECORD]->(cl:Call {value: $call_id})
                        MERGE (ph:Phone {value: $phone})
                        MERGE (cl)-[:CALLER]->(ph)
                        MERGE (c)-[:USES_PHONE]->(ph)
                        """,
                        fir_number=crime.fir_number,
                        call_id=call_id,
                        phone=caller,
                    )
                if callee:
                    session.run(
                        """
                        MATCH (c:Crime {fir_number: $fir_number})-[:CALL_RECORD]->(cl:Call {value: $call_id})
                        MERGE (ph:Phone {value: $phone})
                        MERGE (cl)-[:RECEIVER]->(ph)
                        MERGE (c)-[:USES_PHONE]->(ph)
                        """,
                        fir_number=crime.fir_number,
                        call_id=call_id,
                        phone=callee,
                    )

        return True
    except Exception as exc:
        logger.warning("Neo4j sync failed for crime %s: %s", crime.fir_number, exc)
        return False


def sync_all_crimes(db: Session, *, rebuild: bool = False) -> int:
    if rebuild:
        clear_graph()
    crimes = (
        db.query(CrimeRecord)
        .options(
            joinedload(CrimeRecord.persons),
            joinedload(CrimeRecord.entities),
            joinedload(CrimeRecord.transactions),
            joinedload(CrimeRecord.call_logs),
        )
        .all()
    )
    synced = 0
    for crime in crimes:
        if sync_crime_to_graph(db, crime.id):
            synced += 1
    return synced


def get_network_graph(limit: int = 500, view: str = "investigation") -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node) -> None:
        if node is None:
            return
        node_key = _node_id(node)
        label_type = list(node.labels)[0].lower()
        if view == "investigation" and label_type in SKIP_NODE_TYPES:
            return
        nodes[node_key] = {
            "id": node_key,
            "label": _node_label(node),
            "type": label_type,
            "meta": _node_meta(node),
        }

    def add_edge(source_node, rel, target_node) -> None:
        if source_node is None or target_node is None or rel is None:
            return
        rel_type = rel.type
        if view == "investigation" and rel_type not in INVESTIGATION_RELATIONSHIPS:
            return
        source = _node_id(source_node)
        target = _node_id(target_node)
        if source not in nodes and target not in nodes:
            # ensure at least endpoints exist if not skipped
            add_node(source_node)
            add_node(target_node)
        elif source not in nodes:
            add_node(source_node)
        elif target not in nodes:
            add_node(target_node)
        if source not in nodes or target not in nodes:
            return

        edge_key = (source, target, rel_type)
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        rel_props = dict(rel)
        edges.append(
            {
                "source": source,
                "target": target,
                "relationship": rel_type,
                "label": _edge_label(rel_type, rel_props),
            }
        )

    try:
        with neo4j_session() as session:
            rel_result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE type(r) IN $rel_types
                RETURN a, r, b
                LIMIT $limit
                """,
                rel_types=list(INVESTIGATION_RELATIONSHIPS),
                limit=limit,
            )
            for record in rel_result:
                add_node(record["a"])
                add_node(record["b"])
                add_edge(record["a"], record["r"], record["b"])

            # Orphan investigation nodes (e.g. crime with no edges yet)
            orphan_result = session.run(
                """
                MATCH (n:Crime)
                WHERE NOT (n)-[]-()
                RETURN n
                LIMIT 50
                """,
            )
            for record in orphan_result:
                add_node(record["n"])

    except Exception as exc:
        logger.warning("Failed to fetch network graph: %s", exc)
        return {"nodes": [], "edges": [], "insights": {}}

    insights = _compute_insights(nodes, edges)
    return {"nodes": list(nodes.values()), "edges": edges, "insights": insights}


def _compute_insights(nodes: dict, edges: list) -> dict:
    crimes = sum(1 for n in nodes.values() if n["type"] == "crime")
    persons = sum(1 for n in nodes.values() if n["type"] == "person")
    phones = {n["id"] for n in nodes.values() if n["type"] == "phone"}

    phone_to_crimes: dict[str, set[str]] = {}
    for edge in edges:
        if edge["relationship"] != "USES_PHONE":
            continue
        src, tgt = edge["source"], edge["target"]
        if src.startswith("crime:") and tgt.startswith("phone:"):
            phone_to_crimes.setdefault(tgt, set()).add(src)
        elif tgt.startswith("crime:") and src.startswith("phone:"):
            phone_to_crimes.setdefault(src, set()).add(tgt)

    shared_phones = sum(1 for cases in phone_to_crimes.values() if len(cases) > 1)
    co_suspects = sum(1 for e in edges if e["relationship"] == "CO_SUSPECT")

    return {
        "cases": crimes,
        "people": persons,
        "phones": len(phones),
        "shared_phones": shared_phones,
        "co_suspect_links": co_suspects,
    }
