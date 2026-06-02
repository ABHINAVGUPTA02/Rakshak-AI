from datetime import date

from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord, Person, PersonRole
from app.services.enrichment.graph_sync import sync_crime_to_graph


def seed_sample_data(db: Session) -> None:
    if db.query(CrimeRecord).count() > 0:
        return

    samples = [
        {
            "fir_number": "FIR/2024/001",
            "crime_type": "Theft",
            "description": "Mobile phone stolen at bus stand",
            "district": "Bengaluru Urban",
            "police_station": "Cubbon Park",
            "latitude": 12.9762,
            "longitude": 77.6033,
            "incident_date": date(2024, 3, 15),
            "persons": [
                {"name": "Ravi Kumar", "role": PersonRole.ACCUSED, "age": 28},
                {"name": "Priya S", "role": PersonRole.VICTIM, "age": 32},
            ],
        },
        {
            "fir_number": "FIR/2024/002",
            "crime_type": "Assault",
            "description": "Physical altercation during dispute",
            "district": "Mysuru",
            "police_station": "Vijayanagar",
            "latitude": 12.2958,
            "longitude": 76.6394,
            "incident_date": date(2024, 5, 2),
            "persons": [
                {"name": "Ravi Kumar", "role": PersonRole.ACCUSED, "age": 28},
                {"name": "Anil M", "role": PersonRole.VICTIM, "age": 45},
            ],
        },
        {
            "fir_number": "FIR/2024/003",
            "crime_type": "Cyber Fraud",
            "description": "UPI fraud via phishing link",
            "district": "Bengaluru Urban",
            "police_station": "Electronic City",
            "latitude": 12.8456,
            "longitude": 77.6603,
            "incident_date": date(2024, 7, 20),
            "persons": [
                {"name": "Unknown Suspect", "role": PersonRole.ACCUSED},
                {"name": "Kavya R", "role": PersonRole.VICTIM, "age": 26},
            ],
        },
        {
            "fir_number": "FIR/2024/004",
            "crime_type": "Robbery",
            "description": "Armed robbery at jewelry store",
            "district": "Hubballi",
            "police_station": "Vidyanagar",
            "latitude": 15.3647,
            "longitude": 75.1240,
            "incident_date": date(2024, 9, 10),
            "persons": [
                {"name": "Gang Member A", "role": PersonRole.ACCUSED, "age": 35},
                {"name": "Store Owner", "role": PersonRole.VICTIM, "age": 50},
            ],
        },
        {
            "fir_number": "FIR/2024/005",
            "crime_type": "Theft",
            "description": "Vehicle theft from parking lot",
            "district": "Mangaluru",
            "police_station": "Kadri",
            "latitude": 12.9141,
            "longitude": 74.8560,
            "incident_date": date(2024, 11, 5),
            "persons": [
                {"name": "Ravi Kumar", "role": PersonRole.ACCUSED, "age": 28},
                {"name": "Vehicle Owner", "role": PersonRole.VICTIM, "age": 40},
            ],
        },
    ]

    for sample in samples:
        persons_data = sample.pop("persons")
        crime = CrimeRecord(**sample)
        for p in persons_data:
            crime.persons.append(Person(**p))
        db.add(crime)

    db.commit()

    crimes = db.query(CrimeRecord).all()
    for crime in crimes:
        try:
            sync_crime_to_graph(db, crime.id)
        except Exception:
            pass
