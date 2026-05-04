from datetime import datetime


def competencia_atual():
    hoje = datetime.now()
    return f"{hoje.month:02d}/{hoje.year}"


def ano_atual():
    return str(datetime.now().year)
