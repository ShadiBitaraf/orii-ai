#  in-memory TTL cache
# 2
import datetime
class Cached:
    def __init__(self, ttl_mins=60):
        self.ttl_mins = datetime.timedelta(minutes=ttl_mins)
        self.cached_data = {}

    def is_stale(self, retrievedTime):
        expiry_point = retrievedTime + self.ttl_mins
        return datetime.datetime.now() > expiry_point

    ####### Getter and Setter #######
    def get(self, key_event):
        if key_event in self.cached_data:
            if self.is_stale(self.cached_data[key_event]["retrieved_at"]):
                print("key stale")
                return None
            else:
                return self.cached_data[key_event]["events"]
        else:
            print("key dne. timestamp not cached")
            return None

    def set(self, key_timerange, value_events) -> None:
        self.cached_data[key_timerange] = {
            "events": value_events,
            "retrieved_at": datetime.datetime.now(),
        }


# if __name__ == "__main__":
    ####### Notes #######
    # - the outer dict can have multiple keys: one per date range that's been queried this session.
    # - e.g. :
    # cached_data = {
    #     "2026-07-04": { "events": [...], "retrieved_at": datetime(2026, 7, 4, 9, 0) },
    #     "2026-07-04_2026-07-11": { "events": [...], "retrieved_at": datetime(2026, 7, 4, 9, 5) },
    # }
    # - input of the function is strings, whether its a range or single date
    # - the retrieved_at is the now timestamp on when the setter is called.

    ####### Final Structure form #######

    ### TYPE: dict[str, dict]
    # cached_data = {

    #     ### outer key: str (the date range)
    #     "2026-07-04": {

    #         ### inner key "events": str
    #         ### inner value: list[dict]  ← real Google event objects
    #         "events": [
    #             {"summary": "Dentist", "start": {"dateTime": "..."}},
    #             {"summary": "Lunch",   "start": {"dateTime": "..."}}
    #         ],

    #         ### inner key "retrieved_at": str
    #         ### inner value: datetime object  ← you created this, not Google
    #         "retrieved_at": datetime.datetime(2026, 7, 4, 9, 0, 0)
    #     }
    # }
