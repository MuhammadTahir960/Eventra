def results(response):
    return response.data["results"] if "results" in response.data else response.data
