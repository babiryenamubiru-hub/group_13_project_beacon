import argparse
import csv
from datetime import date, datetime
from pathlib import Path

REQUIRED_COLUMNS = [
    "beacon_id",
    "easting_m",
    "northing_m",
    "condition",
    "construction_activity",
    "flood_exposure",
    "visibility",
    "last_verified",
]

VALID_VALUES = {
    "condition": {"good", "fair", "damaged", "missing"},
    "construction_activity": {"none", "nearby", "active"},
    "flood_exposure": {"low", "medium", "high"},
    "visibility": {"clear", "partly_obscured", "obscured"},
}

CONDITION_POINTS = {"good": 0, "fair": 8, "damaged": 18, "missing": 30}
CONSTRUCTION_POINTS = {"none": 0, "nearby": 12, "active": 22}
FLOOD_POINTS = {"low": 0, "medium": 8, "high": 15}
VISIBILITY_POINTS = {"clear": 0, "partly_obscured": 5, "obscured": 10}


def normalise(value):
    """Remove extra spaces and standardise category text."""
    return str(value).strip().lower().replace(" ", "_")


def verification_age_points(last_verified):
    """Return points based on how long ago the beacon was last verified."""
    if not last_verified or not str(last_verified).strip():
        return 15, "Verification date missing"

    try:
        verified_date = datetime.strptime(str(last_verified).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("last_verified must use YYYY-MM-DD format.")

    if verified_date > date.today():
        raise ValueError("last_verified cannot be a future date.")

    age_days = (date.today() - verified_date).days

    if age_days > 730:
        return 15, f"Last verified {age_days} days ago"
    elif age_days > 365:
        return 10, f"Last verified {age_days} days ago"
    elif age_days > 180:
        return 5, f"Last verified {age_days} days ago"
    return 0, f"Last verified {age_days} days ago"


def classify_priority(score):
    """Convert the numerical score into a priority category."""
    if score >= 65:
        return "URGENT"
    elif score >= 40:
        return "HIGH"
    elif score >= 20:
        return "MODERATE"
    return "LOW"


def recommend_action(priority, condition):
    """Provide a simple recommended next step."""
    if condition == "missing":
        return "Arrange a qualified surveyor-led investigation; do not replace based on this score alone."
    if priority == "URGENT":
        return "Arrange an urgent field assessment by a qualified surveyor."
    if priority == "HIGH":
        return "Schedule a priority field inspection."
    if priority == "MODERATE":
        return "Schedule an inspection and continue monitoring."
    return "Routine monitoring; verify during the next planned inspection."


def assess_beacon(record):
    """Validate one beacon record and return its risk assessment."""
    cleaned = {key: str(record.get(key, "")).strip() for key in REQUIRED_COLUMNS}

    if not cleaned["beacon_id"]:
        raise ValueError("beacon_id is empty.")

    # Coordinates must be numeric. The current scoring model stores but does not score them.
    try:
        easting = float(cleaned["easting_m"])
        northing = float(cleaned["northing_m"])
    except ValueError:
        raise ValueError("easting_m and northing_m must be numeric.")

    for field in ("condition", "construction_activity", "flood_exposure", "visibility"):
        cleaned[field] = normalise(cleaned[field])
        if cleaned[field] not in VALID_VALUES[field]:
            allowed = ", ".join(sorted(VALID_VALUES[field]))
            raise ValueError(f"{field} must be one of: {allowed}.")

    condition_points = CONDITION_POINTS[cleaned["condition"]]
    construction_points = CONSTRUCTION_POINTS[cleaned["construction_activity"]]
    flood_points = FLOOD_POINTS[cleaned["flood_exposure"]]
    visibility_points = VISIBILITY_POINTS[cleaned["visibility"]]
    age_points, age_note = verification_age_points(cleaned["last_verified"])

    raw_score = (
        condition_points
        + construction_points
        + flood_points
        + visibility_points
        + age_points
    )
    score = min(raw_score, 100)
    priority = classify_priority(score)

    result = dict(record)
    result.update({
        "beacon_id": cleaned["beacon_id"],
        "easting_m": easting,
        "northing_m": northing,
        "condition": cleaned["condition"],
        "construction_activity": cleaned["construction_activity"],
        "flood_exposure": cleaned["flood_exposure"],
        "visibility": cleaned["visibility"],
        "last_verified": cleaned["last_verified"],
        "condition_points": condition_points,
        "construction_points": construction_points,
        "flood_points": flood_points,
        "visibility_points": visibility_points,
        "verification_age_points": age_points,
        "verification_age_note": age_note,
        "risk_score": score,
        "priority": priority,
        "recommended_action": recommend_action(priority, cleaned["condition"]),
    })
    return result


def read_csv_dataset(csv_path):
    """Read CSV data, accepting extra columns but requiring the eight core fields."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot find dataset: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("The CSV file is empty or has no header row.")

        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError("Dataset is missing required columns: " + ", ".join(missing))

        return list(reader)


def process_records(records):
    """Assess records, report invalid rows, and prevent duplicate beacon IDs."""
    assessed = []
    seen_ids = set()
    errors = []

    for row_number, record in enumerate(records, start=2):
        beacon_id = str(record.get("beacon_id", "")).strip()
        try:
            if beacon_id in seen_ids:
                raise ValueError(f"Duplicate beacon_id: {beacon_id}")
            result = assess_beacon(record)
            seen_ids.add(beacon_id)
            assessed.append(result)
        except (ValueError, TypeError) as error:
            errors.append(f"CSV row {row_number}: {error}")

    assessed.sort(key=lambda item: item["risk_score"], reverse=True)
    return assessed, errors


def write_report(results, output_path):
    """Write ranked assessments to a new CSV report."""
    if not results:
        print("No valid records to export.")
        return

    fieldnames = list(results[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def print_summary(results):
    """Display the number of beacons in each priority category."""
    print("\n===== BEACON RISK SUMMARY =====")
    print(f"Valid beacons assessed: {len(results)}")
    for category in ("URGENT", "HIGH", "MODERATE", "LOW"):
        count = sum(1 for item in results if item["priority"] == category)
        print(f"{category}: {count}")

    print("\n===== RANKED BEACON RESULTS =====")
    for item in results:
        print(
            f'{item["beacon_id"]}: score {item["risk_score"]}/100 | '
            f'{item["priority"]} | {item["recommended_action"]}'
        )


def run_csv_mode(input_path, output_path):
    records = read_csv_dataset(input_path)
    results, errors = process_records(records)

    print_summary(results)
    if errors:
        print("\n===== RECORDS NEEDING CORRECTION =====")
        for error in errors:
            print(error)

    write_report(results, output_path)
    if results:
        print(f"\nReport saved to: {output_path}")


def run_interactive_mode():
    """Ask the user to enter one beacon record at the terminal."""
    print("\nEnter the details for ONE boundary beacon.")
    print("Use the category options shown in brackets.\n")

    record = {
        "beacon_id": input("Beacon ID (e.g. BB-001): ").strip(),
        "easting_m": input("Easting in metres: ").strip(),
        "northing_m": input("Northing in metres: ").strip(),
        "condition": input("Condition (good/fair/damaged/missing): ").strip(),
        "construction_activity": input("Construction (none/nearby/active): ").strip(),
        "flood_exposure": input("Flood exposure (low/medium/high): ").strip(),
        "visibility": input("Visibility (clear/partly_obscured/obscured): ").strip(),
        "last_verified": input("Last verified date (YYYY-MM-DD; leave blank if unknown): ").strip(),
    }

    result = assess_beacon(record)
    print("\n===== BEACON ASSESSMENT =====")
    for key in (
        "beacon_id", "risk_score", "priority", "recommended_action",
        "condition_points", "construction_points", "flood_points",
        "visibility_points", "verification_age_points", "verification_age_note"
    ):
        print(f"{key}: {result[key]}")

    save = input("\nSave this assessment to interactive_assessment.csv? (y/n): ").strip().lower()
    if save == "y":
        write_report([result], "interactive_assessment.csv")
        print("Assessment saved to interactive_assessment.csv")


def main():
    parser = argparse.ArgumentParser(
        description="Assess and rank boundary beacon inspection priorities."
    )
    parser.add_argument("--csv", help="Input CSV dataset")
    parser.add_argument("--out", default="risk_report.csv", help="Output report filename")
    args = parser.parse_args()

    try:
        if args.csv:
            run_csv_mode(args.csv, args.out)
        else:
            run_interactive_mode()
    except (FileNotFoundError, ValueError) as error:
        print(f"\nERROR: {error}")


if __name__ == "__main__":
    main()