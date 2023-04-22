def handle_task(channel, method, properties, body):
    print("Handling task")
    try:
        # try to parse data and return address from the message body
        task = json.loads(body)
        data = task["data"]
        sensor = task["sensor"]
        href = task["@controls"]["edit"]["href"]
    except KeyError as e:
        # log error
        print(e)
    else:
        # calculate stats
        stats = calculate_stats(task["data"])
        stats["generated"] = datetime.now().isoformat()

        # send the results back to the API
        with requests.Session() as session:
            resp = session.put(
                API_SERVER + href,
                json=stats
            )

        if resp.status_code != 204:
            # log error
            print("Failed PUT")
        else:
            print("Stats updated")
    finally:
        # acknowledge the task regardless of outcome
        print("Task handled")
        channel.basic_ack(delivery_tag=method.delivery_tag)