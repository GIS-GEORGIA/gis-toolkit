# -*- coding: utf-8 -*-
"""გაზიარებული „შაბლონის ნაკრებები“ — ზონა/შაბლონი → ფაილის საბაზისო სახელი.

საერთო მონაცემია ორ ადგილას გამოსაყენებლად: ``gis_box.py``-ის ცალკეული
``TemplateCopier`` sidebar-ხელსაწყოებისთვის და ``tools.zone_intersect``-ის
ჩაშენებული „კოპირება ზონის მიხედვით“ სექციებისთვის (``COPY_SECTIONS``) —
ორივეს ერთი და იგივე მონაცემი სჭირდება, ასე რომ აქ ცალკეა, დუბლირების
გარეშე და წრიული იმპორტის რისკის გარეშე (``zone_intersect`` ვერ
დაიმპორტებდა ამ მონაცემს პირდაპირ ``gis_box``-იდან, რადგან ეს უკანასკნელი
თავად იმპორტებს ``zone_intersect``-ს).

ახალი შაბლონისთვის უბრალოდ დაამატე ერთი ჩანაწერი: ``id`` უნიკალური,
``templates``-ში ზონა→base-name (გაფართოებების გარეშე).
"""

TEMPLATE_SETS = [
    {"id": "riverbank",
     "name_en": "Riverbank line", "name_ka": "მდინარის ნაპირი",
     "templates": {"37": "riverbank_line37", "38": "riverbank_line38"}},
    {"id": "gas_crossing",
     "name_en": "Gas pipe crossing", "name_ka": "გაზსადენის გადაკვეთა",
     "templates": {"37": "Gas_Pipe_Crossing37", "38": "Gas_Pipe_Crossing38"}},
    {"id": "protzone_crossing",
     "name_en": "Protection zone crossing", "name_ka": "დაცვის ზონების გადაკვეთა",
     "templates": {"37": "Gas_Pipe_ProtZone_Crossing37", "38": "Gas_Pipe_ProtZone_Crossing38"}},
    {"id": "utm_grid",
     "name_en": "UTM grid", "name_ka": "UTM ბადე",
     "zoned": False,
     "templates": {"grid": "Georgia_UTM_37_38_grid"}},
]


def get(set_id):
    """ერთი კონფიგურაცია id-ით (KeyError — თუ ვერ მოიძებნა)."""
    for cfg in TEMPLATE_SETS:
        if cfg["id"] == set_id:
            return cfg
    raise KeyError(set_id)
