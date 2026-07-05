WORKOUT_TYPE_LABELS = {
    0: "Default",
    1: "Race",
    2: "Long Run",
    3: "Workout",
    10: "Default",
    11: "Race",
    12: "Workout",
}

CSV_COLUMNS = [
    "id",
    "name",
    "description",
    "type",
    "sport_type",
    "workout_type_raw",
    "workout_type_label",
    "start_date_utc",
    "start_date_local",
    "timezone",
    "distance_m",
    "distance_mi",
    "moving_time_s",
    "elapsed_time_s",
    "total_elevation_gain_m",
    "total_elevation_gain_ft",
    "average_speed_mps",
    "max_speed_mps",
    "average_heartrate",
    "max_heartrate",
    "average_cadence",
    "average_watts",
    "weighted_average_watts",
    "kilojoules",
    "calories",
    "suffer_score",
    "perceived_exertion",
    "gear_id",
    "achievement_count",
    "pr_count",
    "gold_pr_count",
    "silver_pr_count",
    "bronze_pr_count",
    "kom_count",
    "top10_count",
    "kudos_count",
    "comment_count",
    "athlete_count",
    "photo_count",
    "total_photo_count",
    "commute",
    "trainer",
    "manual",
    "private",
    "flagged",
    "device_name",
    "start_lat",
    "start_lng",
]


def _tier_counts(segment_efforts):
    """Derive gold/silver/bronze PR counts and KOM/top-10 counts from segment efforts.

    Strava's own `achievement_count`/`pr_count` don't break down by tier, so this
    reads `pr_rank` (1/2/3 = gold/silver/bronze PR) and `kom_rank` (1 = KOM/QOM,
    2-10 = other top-10 placement) off each segment effort.
    """
    gold = silver = bronze = kom = top10 = 0
    for effort in segment_efforts or []:
        pr_rank = effort.get("pr_rank")
        if pr_rank == 1:
            gold += 1
        elif pr_rank == 2:
            silver += 1
        elif pr_rank == 3:
            bronze += 1

        kom_rank = effort.get("kom_rank")
        if kom_rank == 1:
            kom += 1
        elif kom_rank and 2 <= kom_rank <= 10:
            top10 += 1
    return gold, silver, bronze, kom, top10


def build_record(summary, detail=None):
    """Combine a summary activity (from /athlete/activities) with its detail
    payload (from /activities/{id}) into one flat CSV row."""
    detail = detail or {}
    segment_efforts = detail.get("segment_efforts", [])
    gold, silver, bronze, kom, top10 = _tier_counts(segment_efforts)

    distance_m = summary.get("distance")
    elevation_m = summary.get("total_elevation_gain")
    workout_type = summary.get("workout_type")
    start_latlng = summary.get("start_latlng") or []

    return {
        "id": summary.get("id"),
        "name": summary.get("name"),
        "description": detail.get("description"),
        "type": summary.get("type"),
        "sport_type": summary.get("sport_type"),
        "workout_type_raw": workout_type,
        "workout_type_label": WORKOUT_TYPE_LABELS.get(workout_type, ""),
        "start_date_utc": summary.get("start_date"),
        "start_date_local": summary.get("start_date_local"),
        "timezone": summary.get("timezone"),
        "distance_m": distance_m,
        "distance_mi": round(distance_m / 1609.34, 3) if distance_m is not None else None,
        "moving_time_s": summary.get("moving_time"),
        "elapsed_time_s": summary.get("elapsed_time"),
        "total_elevation_gain_m": elevation_m,
        "total_elevation_gain_ft": round(elevation_m * 3.28084, 1) if elevation_m is not None else None,
        "average_speed_mps": summary.get("average_speed"),
        "max_speed_mps": summary.get("max_speed"),
        "average_heartrate": summary.get("average_heartrate"),
        "max_heartrate": summary.get("max_heartrate"),
        "average_cadence": summary.get("average_cadence"),
        "average_watts": summary.get("average_watts"),
        "weighted_average_watts": summary.get("weighted_average_watts"),
        "kilojoules": summary.get("kilojoules"),
        "calories": detail.get("calories"),
        "suffer_score": detail.get("suffer_score", summary.get("suffer_score")),
        "perceived_exertion": detail.get("perceived_exertion"),
        "gear_id": summary.get("gear_id"),
        "achievement_count": summary.get("achievement_count"),
        "pr_count": detail.get("pr_count", summary.get("pr_count")),
        "gold_pr_count": gold,
        "silver_pr_count": silver,
        "bronze_pr_count": bronze,
        "kom_count": kom,
        "top10_count": top10,
        "kudos_count": summary.get("kudos_count"),
        "comment_count": summary.get("comment_count"),
        "athlete_count": summary.get("athlete_count"),
        "photo_count": summary.get("photo_count"),
        "total_photo_count": detail.get("total_photo_count", summary.get("total_photo_count")),
        "commute": summary.get("commute"),
        "trainer": summary.get("trainer"),
        "manual": summary.get("manual"),
        "private": summary.get("private"),
        "flagged": summary.get("flagged"),
        "device_name": detail.get("device_name"),
        "start_lat": start_latlng[0] if len(start_latlng) == 2 else None,
        "start_lng": start_latlng[1] if len(start_latlng) == 2 else None,
    }
