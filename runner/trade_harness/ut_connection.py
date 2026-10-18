"""Windows COM connection to the explicitly configured 1C reference database."""
from __future__ import annotations

import os


def connect():
    import win32com.client

    def quoted(value):
        return '"' + value.replace('"', '""') + '"'

    password = os.environ.get("CTM_UT_PASSWORD")
    if password is None:
        raise RuntimeError("Set CTM_UT_PASSWORD in the process environment")
    fields = {
        "Srvr": os.environ.get("CTM_UT_HOST", "localhost"),
        "Ref": os.environ.get("CTM_UT_INFOBASE", "UTrecover"),
        "Usr": os.environ.get("CTM_UT_USER", "Администратор"),
        "Pwd": password,
    }
    connector = win32com.client.Dispatch(os.environ.get("CTM_UT_COM_PROGID", "V85.COMConnector"))
    return connector.Connect(";".join(f"{key}={quoted(value)}" for key, value in fields.items()) + ";")


def query(ib, text, **parameters):
    statement = ib.NewObject("Запрос")
    statement.Text = text
    for name, value in parameters.items():
        statement.SetParameter(name, value)
    selection = statement.Execute().Choose()
    while selection.Next():
        yield selection
