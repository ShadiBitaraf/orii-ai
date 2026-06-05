#  in-memory TTL cache
# 2

import datetime
class Cached:
    cached_data = {}
    def __init__(self, ttl_mins=60):
        self.ttl = datetime.timedelta(minutes=ttl_mins)

    # cached_data = {
    #     "today": {
    #         "events": [...],
    #         "retrieved_at": datetime.datetime(2026, 5, 28, 10, 0, 0)
    #     }
    # }

    def is_stale(self):
        timestamp_str = cached_data["retrieved_at"]
        retrieved_time = datetime.datetime.fromisoformat(timestamp_str)
        ttl = retrieved_time + datetime.timedelta(hours=1)

        if ttl < datetime.datetime.now():
            print("Cache is stale")
            return True
        print("Cache is fresh")
        return False


    #getter and setter query.py will use to check for cached data and set cached data if it doesn't exit
    def get(self, key) -> Optional[dict]:
        if key not in self.cached_data:
            print("key dne. timestamp not cached")
            return None
        elif self.is_stale(cached_data[key]):
            print("key stale. timestamp cached")
            return None
        return cached_data[key]

    def set(key, value) -> None:
        cached_data[key] = value

# my question for now and future is if im defining functions and classes that i need to 
#define inputs and return values for, how do i know the other classes that feed these functions
#inputs have as return types. like in the setter func, how do i know what is the type of the value input
#that the calendar or query file provides? what do i know the type of key

#key is a str (a date string like "2026-05-28"), value is a list[dict] (a list of Google Calendar event objects).


    # def main():
    #     inner_dict = cached_data[0] 
    #     if is_stale(inner_dict) == False:
    #         return cached_data[0]["data"] #TODO: or whatever the key is for the events data in the inner dict. idk what the key is. maybe "events" or "data" or something else. i need to check how the inner dict is defined and what keys it has.
    #     if is_stale() == True:
    #         return None


    # if __name__ == "__main__":
    #     main()




