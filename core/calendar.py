# Google API calls (new, clean)
# 3
# "go fetch events from Google API for this date range"

#define retrieve cal data function. calls api and gets data for a time range.
# it returns (whats the format of the data)

#define a result object?
#if cache returns data (whats the returning format), dont call api, set result = cache[data]

#if cache returns none:
# call the retrieve cal data function


#if key dne, return false(or sth). 
# if it does, see if its cached. 
    #if cached returns data, set result = cache[data]
    #if cached returns none, call api to get data
        #and tehn send it to get cached? idk how this part works