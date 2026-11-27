# -*- coding: utf-8 -*-
"""რუკის სერვისების სია — GUI-ს გარეშე (V2 გვერდი იყენებს; კლასიკური ``tools.map_services`` იგივე ფორმატს კითხულობს).

``map_services.txt`` ფორმატი: სახელის ხაზი, შემდეგ ``http…`` URL-ის ხაზი; ცარიელი ხაზები და ``Services:``
სათაური იგნორირდება. ახლის დამატება ფაილის რედაქტირებით, კოდის შეხების გარეშე.
"""
import os

# ფაილისგან დამოუკიდებლად ყოველთვის ემატება
EXTRA_SERVICES = [
    ("NAPR ორთოფოტო 2023 (WMS)",
     "https://mp.napr.gov.ge/ORTHO_2023_BLK2/ows?service=wms&version=1.3.0&request=GetCapabilities"),
]


def services_file():
    """მომხმარებლის ჩასაწერი კონფიგის საქაღალდე ჯერ, შემდეგ ჩაშენებული ნაგულისხმევი (იგივე წესი, რაც კლასიკურში)."""
    from tools.apppaths import config_read_path
    return config_read_path("map_services.txt")


def load_services(path=None):
    """``[(სახელი, URL), …]`` + ``EXTRA_SERVICES``."""
    path = path or services_file()
    services, name = [], None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.lower().startswith("services"):
                    name = None
                    continue
                if line.startswith("http"):
                    if name:
                        services.append((name, line))
                        name = None
                else:
                    name = line
    return services + EXTRA_SERVICES
