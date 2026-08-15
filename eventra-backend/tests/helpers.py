def results(response):
    return response.data.get("results", response.data)
