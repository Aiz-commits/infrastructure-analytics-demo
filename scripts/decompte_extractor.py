
from decimal import Decimal, ROUND_HALF_UP
from openpyxl import load_workbook


def amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing or invalid financial amount")

    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


def extract_decompte(file):
    """
    Extract and verify financial values from a
    supported construction project payment statement.
    The source workbook is not modified.
    """

    workbook = load_workbook(
        file,
        read_only=True,
        data_only=True
    )

    try:
        sheet = workbook.worksheets[0]

        # Detect the supported summary layouts
        if sheet["A39"].value == "Retenue de Garantie":
            works_row = 37
            retention_row = 39
            net_row = 44
            vat_row = 45
            ttc_row = 46

        elif sheet["A41"].value == "Retenue de Garantie":
            works_row = 39
            retention_row = 41
            net_row = 46
            vat_row = 47
            ttc_row = 48

        else:
            raise ValueError(
                "Unsupported décompte layout. "
                "Please verify the source worksheet."
            )

        works = amount(sheet[f"D{works_row}"].value)

        # Cumulative financial values for continuity checks
        cumulative = amount(sheet[f"B{works_row}"].value)

        previous_raw = sheet[f"C{works_row}"].value

        previous_cumulative = (
            amount(previous_raw)
            if previous_raw is not None
            else None
        )

        retention = amount(sheet[f"D{retention_row}"].value)
        net = amount(sheet[f"D{net_row}"].value)
        vat = amount(sheet[f"D{vat_row}"].value)
        ttc = amount(sheet[f"D{ttc_row}"].value)

        expected_retention = amount(works * Decimal("0.10"))
        expected_net = amount(works - expected_retention)
        expected_vat = amount(expected_net * Decimal("0.20"))
        expected_ttc = amount(expected_net + expected_vat)

        differences = {
            "Retention": abs(retention - expected_retention),
            "Net HT": abs(net - expected_net),
            "VAT": abs(vat - expected_vat),
            "TTC": abs(ttc - expected_ttc)
        }

        status = (
            "OK"
            if all(x <= Decimal("0.01") for x in differences.values())
            else "REVIEW REQUIRED"
        )

        return {
            "Works HT": float(works),
            "Cumulative HT": float(cumulative),
            "Previous cumulative HT": (
                float(previous_cumulative)
                if previous_cumulative is not None
                else None
            ),
            "Retention": float(retention),
            "Net HT": float(net),
            "VAT": float(vat),
            "TTC": float(ttc),
            "Status": status,
            "Maximum difference": float(max(differences.values()))
        }

    finally:
        workbook.close()
