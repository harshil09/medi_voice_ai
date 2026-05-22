"""Run once: python names.py"""
from database import get_connection, create_tables

create_tables()

conn = get_connection()
cursor = conn.cursor()

if cursor.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] > 0:
    conn.close()
    print("Already seeded. Delete hospital.db to re-seed.")
    raise SystemExit(0)

cursor.executemany(
    "INSERT INTO doctors (name, specialty, available, emergency) VALUES (?, ?, ?, ?)",
    [
        ("Dr. Shah", "cardiologist", 1, 1),
        ("Dr. Mehta", "cardiologist", 1, 0),
        ("Dr. Patel", "general", 1, 0),
        ("Dr. Smith", "general", 1, 0),
        ("Dr. Kapoor", "orthopedic", 1, 0),
    ],
)

doctor_ids = [r[0] for r in cursor.execute("SELECT id FROM doctors")]
slots = [
    (did, date, time, 0)
    for did in doctor_ids
    for date in ("2026-05-26", "2026-05-27", "2026-05-28")
    for time in ("09:00", "10:30", "13:00", "14:30", "16:00")
]
cursor.executemany(
    "INSERT INTO doctor_slots (doctor_id, slot_date, slot_time, is_booked) VALUES (?, ?, ?, ?)",
    slots,
)

cursor.executemany(
    "INSERT INTO insurance_providers (name, accepted) VALUES (?, ?)",
    [
        ("Blue Cross Blue Shield", 1),
        ("Aetna", 1),
        ("UnitedHealthcare", 1),
        ("Medicare", 1),
        ("Medicaid", 1),
        ("Cigna", 0),
    ],
)

conn.commit()
conn.close()
print("Seeded successfully.")
