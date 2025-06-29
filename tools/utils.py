import json


def pretty_print(data):
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    print(json.dumps(data, indent=2, ensure_ascii=False))
