import json

def pretty_print(data):
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif isinstance(data, list) and all(hasattr(item, "model_dump") for item in data):
        data = [item.model_dump() for item in data]
    print(json.dumps(data, indent=2, ensure_ascii=False))
