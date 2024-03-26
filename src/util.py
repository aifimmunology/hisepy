import toml


def load_config(file_path=".\\config.toml"):
    """
    Load and return configuration from a TOML file.

    Args:
        file_path (str): Path to the TOML file.

    Returns:
        dict: Configuration data.
    """
    with open(file_path, "r") as config_file:
        config = toml.load(config_file)
    return config
