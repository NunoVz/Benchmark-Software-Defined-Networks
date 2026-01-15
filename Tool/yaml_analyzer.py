import yaml


def parse_yaml(filename):
    with open(filename, 'r') as file:
        data = yaml.safe_load(file)
    return data


def yaml_analizer(controller_name):

    if controller_name == "onos":
        filename = "API_Specifications/onos_copy.yaml"
    elif controller_name == "odl":
        filename = "API_Specifications/odl.yaml"
    elif controller_name == 'ryu':
        filename = "API_Specifications/ryu.yaml"
    else:
        print("File does not exists")
    api_spec = parse_yaml(filename)
    return api_spec
