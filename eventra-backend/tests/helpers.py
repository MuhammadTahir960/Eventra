def results(response):
    return (
        response.data.get("results", response.data)
        if isinstance(response.data, dict)
        else response.data
    )
