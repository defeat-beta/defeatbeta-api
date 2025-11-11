from importlib.resources import files

def load_sql(template_name: str, **kwargs) -> str:
    if not template_name or any(c in template_name for c in ['/', '\\', '..']):
        raise ValueError(f"Invalid template name: {template_name}")

    try:
        base_path = files("defeatbeta_api.data.sql")
        file_path = base_path / f"{template_name}.sql"
    except ModuleNotFoundError:
        raise FileNotFoundError(f"SQL template directory 'defeatbeta_api.data.sql' not found")

    try:
        with file_path.open('r', encoding='utf-8') as file:
            query = file.read().strip()
            if not query:
                raise ValueError(f"SQL template {template_name}.sql is empty")
        return query.format(**kwargs)
    except FileNotFoundError:
        raise FileNotFoundError(f"SQL template {template_name}.sql not found in {base_path}")
    except KeyError as e:
        raise KeyError(f"Missing parameter for SQL template: {e}")