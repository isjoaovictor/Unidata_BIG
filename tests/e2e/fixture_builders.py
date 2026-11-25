"""Pure-Python synthetic Olist fixture builders & opaque-box deliverable validators.

This module intentionally uses ONLY Python standard library modules (`csv`, `json`,
`pathlib`, `re`, `shutil`, `zipfile`) so it imports cleanly before any third-party
dependencies are installed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ORDERS_HEADER = [
    "order_id",
    "customer_id",
    "order_status",
    "order_purchase_timestamp",
]
ORDER_ITEMS_HEADER = [
    "order_id",
    "order_item_id",
    "product_id",
    "price",
    "freight_value",
]
CUSTOMERS_HEADER = ["customer_id", "customer_unique_id"]
PRODUCTS_HEADER = ["product_id", "product_category_name"]
TRANSLATION_HEADER = ["product_category_name", "product_category_name_english"]
PAYMENTS_HEADER = [
    "order_id",
    "payment_sequential",
    "payment_type",
    "payment_installments",
    "payment_value",
]

PRIMARY_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "primary"


def _write_csv(
    path: Path,
    header: list[str],
    rows: list[list[object]],
    *,
    encoding: str = "utf-8",
    newline_str: str = "\n",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh, lineterminator=newline_str)
        writer.writerow(header)
        writer.writerows(rows)


def write_dataset(
    target_dir: Path,
    *,
    orders: list[list[object]],
    order_items: list[list[object]],
    customers: list[list[object]],
    products: list[list[object]],
    translations: list[list[object]] | None = None,
    payments: list[list[object]] | None = None,
    encoding: str = "utf-8",
    lineterminator: str = "\n",
) -> Path:
    """Write a complete synthetic Olist CSV set to `target_dir`."""
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        target_dir / "olist_orders_dataset.csv",
        ORDERS_HEADER,
        orders,
        encoding=encoding,
        newline_str=lineterminator,
    )
    _write_csv(
        target_dir / "olist_order_items_dataset.csv",
        ORDER_ITEMS_HEADER,
        order_items,
        encoding=encoding,
        newline_str=lineterminator,
    )
    _write_csv(
        target_dir / "olist_customers_dataset.csv",
        CUSTOMERS_HEADER,
        customers,
        encoding=encoding,
        newline_str=lineterminator,
    )
    _write_csv(
        target_dir / "olist_products_dataset.csv",
        PRODUCTS_HEADER,
        products,
        encoding=encoding,
        newline_str=lineterminator,
    )
    if translations is not None:
        _write_csv(
            target_dir / "product_category_name_translation.csv",
            TRANSLATION_HEADER,
            translations,
            encoding=encoding,
            newline_str=lineterminator,
        )
    if payments is not None:
        _write_csv(
            target_dir / "olist_order_payments_dataset.csv",
            PAYMENTS_HEADER,
            payments,
            encoding=encoding,
            newline_str=lineterminator,
        )
    return target_dir


def copy_primary_fixture(
    target_dir: Path,
    *,
    include_translation: bool = True,
    exclude_files: set[str] | None = None,
) -> Path:
    """Copy static golden `primary` fixture CSVs into an isolated temp directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    skip = set(exclude_files or set())
    if not include_translation:
        skip.add("product_category_name_translation.csv")
    for csv_path in PRIMARY_FIXTURE_DIR.glob("*.csv"):
        if csv_path.name in skip:
            continue
        shutil.copy2(csv_path, target_dir / csv_path.name)
    return target_dir


def build_fix_multi_pay(target_dir: Path) -> Path:
    """FIX-MULTI-PAY: leading-zero IDs, multi-item orders, freight, split payments trap."""
    orders = [
        ["000123", "000001", "delivered", "2018-05-10 12:00:00"],
        ["000456", "000002", "delivered", "2018-05-12 12:00:00"],
    ]
    order_items = [
        ["000123", "1", "000010", "100.00", "25.00"],
        ["000123", "2", "000011", "50.00", "15.00"],
        ["000456", "1", "000010", "200.00", "20.00"],
    ]
    customers = [
        ["000001", "000901"],
        ["000002", "000902"],
    ]
    products = [
        ["000010", "cama_mesa_banho"],
        ["000011", "beleza_saude"],
    ]
    translations = [
        ["cama_mesa_banho", "bed_bath_table"],
        ["beleza_saude", "health_beauty"],
    ]
    payments = [
        ["000123", "1", "voucher", "1", "30.00"],
        ["000123", "2", "credit_card", "2", "120.00"],
        ["000123", "3", "credit_card", "1", "40.00"],
        ["000456", "1", "credit_card", "1", "110.00"],
        ["000456", "2", "boleto", "1", "110.00"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
        payments=payments,
    )


def build_fix_repeat(target_dir: Path) -> Path:
    """FIX-REPEAT: 6 customer_unique_ids across 12 distinct customer_ids and 12 orders."""
    orders = []
    order_items = []
    customers = []
    dates_a = [
        "2017-06-05 12:00:00",
        "2017-07-05 12:00:00",
        "2017-08-05 12:00:00",
        "2017-09-05 12:00:00",
        "2017-10-05 12:00:00",
        "2017-11-05 12:00:00",
    ]
    dates_b = [
        "2018-05-01 12:00:00",
        "2018-05-10 12:00:00",
        "2018-06-01 12:00:00",
        "2018-06-15 12:00:00",
        "2018-07-01 12:00:00",
        "2018-07-15 12:00:00",
    ]
    for i in range(1, 7):
        uid = f"U_REP_{i:02d}"
        cid1 = f"CID_A_{i:02d}"
        cid2 = f"CID_B_{i:02d}"
        oid1 = f"ORD_A_{i:02d}"
        oid2 = f"ORD_B_{i:02d}"
        customers.append([cid1, uid])
        customers.append([cid2, uid])
        orders.append([oid1, cid1, "delivered", dates_a[i - 1]])
        orders.append([oid2, cid2, "delivered", dates_b[i - 1]])
        order_items.append([oid1, "1", "P_REP_1", f"{100.0 + i * 10:.2f}", "15.00"])
        order_items.append([oid2, "1", "P_REP_2", f"{150.0 + i * 10:.2f}", "15.00"])

    products = [
        ["P_REP_1", "cama_mesa_banho"],
        ["P_REP_2", "beleza_saude"],
    ]
    translations = [
        ["cama_mesa_banho", "bed_bath_table"],
        ["beleza_saude", "health_beauty"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
    )


def build_fix_seasonal(target_dir: Path) -> Path:
    """FIX-SEASONAL: 12 delivered orders with 2017-11 spike (60% revenue) & 2018-11 YoY."""
    specs = [
        ("ORD_S01", "C_S01", "U_S01", "2017-10-10 12:00:00", "P_TECH", "100.00"),
        ("ORD_S02", "C_S02", "U_S02", "2017-10-15 12:00:00", "P_TECH", "100.00"),
        ("ORD_S03", "C_S03", "U_S03", "2017-11-24 12:00:00", "P_BED", "750.00"),
        ("ORD_S04", "C_S04", "U_S04", "2017-11-24 12:00:00", "P_BED", "750.00"),
        ("ORD_S05", "C_S05", "U_S05", "2017-11-25 12:00:00", "P_BED", "750.00"),
        ("ORD_S06", "C_S06", "U_S06", "2017-11-26 12:00:00", "P_BED", "750.00"),
        ("ORD_S07", "C_S07", "U_S07", "2017-12-10 12:00:00", "P_HB", "200.00"),
        ("ORD_S08", "C_S08", "U_S08", "2017-12-20 12:00:00", "P_HB", "200.00"),
        ("ORD_S09", "C_S09", "U_S09", "2018-10-10 12:00:00", "P_TECH", "300.00"),
        ("ORD_S10", "C_S10", "U_S10", "2018-10-15 12:00:00", "P_TECH", "300.00"),
        ("ORD_S11", "C_S11", "U_S11", "2018-11-20 12:00:00", "P_BED", "400.00"),
        ("ORD_S12", "C_S12", "U_S12", "2018-11-25 12:00:00", "P_BED", "400.00"),
    ]
    orders = [[o, c, "delivered", dt] for o, c, _, dt, _, _ in specs]
    order_items = [[o, "1", p, pr, "20.00"] for o, _, _, _, p, pr in specs]
    customers = [[c, u] for _, c, u, _, _, _ in specs]
    products = [
        ["P_BED", "cama_mesa_banho"],
        ["P_TECH", "informatica_acessorios"],
        ["P_HB", "beleza_saude"],
    ]
    translations = [
        ["cama_mesa_banho", "bed_bath_table"],
        ["informatica_acessorios", "computers_accessories"],
        ["beleza_saude", "health_beauty"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
    )


def build_fix_small_rfm(target_dir: Path, variant: str = "A") -> Path:
    """FIX-SMALL-RFM variants:
    - A: 3 delivered customers (< 4 min_customers)
    - B: 5 customers with only 2 distinct (R, F, M) tuples
    - C: 6 customers with identical (R, F, M) (zero variance)
    """
    if variant == "A":
        specs = [
            ("ORD_SR1", "C_SR1", "U_SR1", "2018-05-01 12:00:00", "P_1", "100.00"),
            ("ORD_SR2", "C_SR2", "U_SR2", "2018-06-01 12:00:00", "P_2", "200.00"),
            ("ORD_SR3", "C_SR3", "U_SR3", "2018-07-01 12:00:00", "P_1", "300.00"),
        ]
    elif variant == "B":
        specs = [
            ("ORD_SR1", "C_SR1", "U_SR1", "2018-06-01 12:00:00", "P_1", "100.00"),
            ("ORD_SR2", "C_SR2", "U_SR2", "2018-06-01 12:00:00", "P_1", "100.00"),
            ("ORD_SR3", "C_SR3", "U_SR3", "2018-07-01 12:00:00", "P_2", "250.00"),
            ("ORD_SR4", "C_SR4", "U_SR4", "2018-07-01 12:00:00", "P_2", "250.00"),
            ("ORD_SR5", "C_SR5", "U_SR5", "2018-07-01 12:00:00", "P_2", "250.00"),
        ]
    elif variant == "C":
        specs = [
            (f"ORD_ZC{i}", f"C_ZC{i}", f"U_ZC{i}", "2018-07-01 12:00:00", "P_1", "100.00")
            for i in range(1, 7)
        ]
    else:
        raise ValueError(f"Unknown FIX-SMALL-RFM variant: {variant}")

    orders = [[o, c, "delivered", dt] for o, c, _, dt, _, _ in specs]
    order_items = [[o, "1", p, pr, "10.00"] for o, _, _, _, p, pr in specs]
    customers = [[c, u] for _, c, u, _, _, _ in specs]
    products = [["P_1", "cama_mesa_banho"], ["P_2", "beleza_saude"]]
    translations = [
        ["cama_mesa_banho", "bed_bath_table"],
        ["beleza_saude", "health_beauty"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
    )


def build_fix_no_trans(target_dir: Path) -> Path:
    """FIX-NO-TRANS: 4 required CSVs without translation CSV, includes null/blank category."""
    return copy_primary_fixture(target_dir, include_translation=False)


def build_fix_no_deliv(target_dir: Path) -> Path:
    """FIX-NO-DELIV: 5 non-delivered orders (canceled/unavailable/shipped/invoiced/created)."""
    statuses = ["canceled", "unavailable", "shipped", "invoiced", "created"]
    orders = [
        [f"ORD_ND{i}", f"C_ND{i}", st, f"2018-05-0{i} 12:00:00"]
        for i, st in enumerate(statuses, start=1)
    ]
    order_items = [
        [f"ORD_ND{i}", "1", "P_ND1", f"{50.0 * i:.2f}", "10.00"]
        for i in range(1, 6)
    ]
    customers = [[f"C_ND{i}", f"U_ND{i}"] for i in range(1, 6)]
    products = [["P_ND1", "cama_mesa_banho"]]
    translations = [["cama_mesa_banho", "bed_bath_table"]]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
    )


def build_fix_bom_long(target_dir: Path) -> Path:
    """FIX-BOM-LONG: UTF-8 BOM + CRLF + quoted comma + 85-char category + leading-zero IDs."""
    long_cat = "eletrodomesticos_de_cozinha_industrial_e_automacao_residencial_premium_linha_completa"
    assert len(long_cat) >= 85
    orders = [
        ["00001", "00011", "delivered", "2018-01-10 12:00:00"],
        ["00002", "00012", "delivered", "2018-02-10 12:00:00"],
        ["00003", "00013", "delivered", "2018-03-10 12:00:00"],
        ["00004", "00014", "delivered", "2018-04-10 12:00:00"],
        ["00005", "00015", "delivered", "2018-05-10 12:00:00"],
    ]
    order_items = [
        ["00001", "1", "00101", "300.00", "10.00"],
        ["00002", "1", "00102", "250.00", "10.00"],
        ["00003", "1", "00101", "200.00", "10.00"],
        ["00004", "1", "00102", "150.00", "10.00"],
        ["00005", "1", "00101", "100.00", "10.00"],
    ]
    customers = [[f"0001{i}", f"0009{i}"] for i in range(1, 6)]
    products = [
        ["00101", long_cat],
        ["00102", "Categoria, Especial"],
    ]
    translations = [
        [long_cat, long_cat],
        ["Categoria, Especial", "Special, Category"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
        encoding="utf-8-sig",
        lineterminator="\r\n",
    )


def build_fix_large_batch(target_dir: Path, n_orders: int = 2000) -> Path:
    """Generate a deterministic N-order dataset for performance & scale testing."""
    orders = []
    order_items = []
    customers = []
    for i in range(1, n_orders + 1):
        oid = f"ORD_LG_{i:05d}"
        cid = f"CID_LG_{i:05d}"
        uid = f"UID_LG_{(i % 400):04d}"
        month = (i % 12) + 1
        year = 2017 if i <= n_orders // 2 else 2018
        day = (i % 28) + 1
        orders.append([oid, cid, "delivered", f"{year}-{month:02d}-{day:02d} 12:00:00"])
        customers.append([cid, uid])
        prod = f"P_LG_{(i % 4) + 1}"
        price = 50.0 + float((i % 20) * 15)
        order_items.append([oid, "1", prod, f"{price:.2f}", "15.00"])

    products = [
        ["P_LG_1", "cama_mesa_banho"],
        ["P_LG_2", "beleza_saude"],
        ["P_LG_3", "informatica_acessorios"],
        ["P_LG_4", "esporte_lazer"],
    ]
    translations = [
        ["cama_mesa_banho", "bed_bath_table"],
        ["beleza_saude", "health_beauty"],
        ["informatica_acessorios", "computers_accessories"],
        ["esporte_lazer", "sports_leisure"],
    ]
    return write_dataset(
        target_dir,
        orders=orders,
        order_items=order_items,
        customers=customers,
        products=products,
        translations=translations,
    )


# ---------------------------------------------------------------------------
# Opaque-box deliverable validators (always-on synthetic + gated live tests)
# ---------------------------------------------------------------------------


def validate_readme_content(
    readme_path: Path,
    *,
    repo_root: Path | None = None,
    check_links: bool = True,
) -> list[str]:
    """Validate Unidata README.md against R3 and tasks.md acceptance criteria."""
    errors: list[str] = []
    if not readme_path.is_file():
        return [f"README.md not found at {readme_path}"]

    try:
        text = readme_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"README.md is not valid UTF-8: {exc}"]

    if "\ufffd" in text:
        errors.append("README.md contains UTF-8 replacement character (\\ufffd).")

    non_empty_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not non_empty_lines or non_empty_lines[0] != "# Unidata":
        errors.append(
            "README.md must start with exact H1 title '# Unidata' "
            f"(found: {non_empty_lines[0] if non_empty_lines else '<empty>'})."
        )

    lower = text.lower()
    checks = [
        ("project/problem summary", any(k in lower for k in ("problema", "resumo", "e-commerce insights", "olist"))),
        (
            "architecture/data flow",
            all(
                re.search(rf"\b{re.escape(k)}\b", lower)
                for k in ("loader", "pipeline", "analytics", "segmentation", "recommendations")
            )
            and bool(re.search(r"\bapp\.py\b", lower)),
        ),
        ("pip install requirements.txt", "pip install" in lower and "requirements.txt" in lower),
        ("Kaggle Olist URL", "kaggle.com/datasets/olistbr/brazilian-ecommerce" in lower),
        (
            "all 5 Olist CSV filenames",
            all(
                fn in lower
                for fn in (
                    "olist_orders_dataset.csv",
                    "olist_order_items_dataset.csv",
                    "olist_customers_dataset.csv",
                    "olist_products_dataset.csv",
                    "product_category_name_translation.csv",
                )
            ),
        ),
        ("data/ directory placement", "data/" in lower or "data\\" in lower),
        ("streamlit run app.py command", "streamlit run app.py" in lower),
        ("pytest command", "pytest" in lower),
        (
            "RFM/K-means parameters (k=4, random_state=42, n_init=10)",
            bool(re.search(r"(?:random_state\s*=\s*42|\b42\b)", lower))
            and bool(re.search(r"(?:n_init\s*=\s*10|\b10\b)", lower))
            and bool(re.search(r"(?:\bk\s*=\s*4\b|\bn_clusters\s*=\s*4\b)", lower)),
        ),
        ("CC BY-NC-SA 4.0 license", "cc by-nc-sa 4.0" in lower),
        ("non-commercial restriction", "não comercial" in lower or "nao comercial" in lower or "non-commercial" in lower),
        ("non-causal / limitations", "causal" in lower or "previs" in lower or "limita" in lower),
        ("Impeccable honest status note", "impeccable" in lower),
    ]
    for label, ok in checks:
        if not ok:
            errors.append(f"README.md missing required content: {label}.")

    if "impeccable" in lower:
        claim_verb_re = re.compile(
            r"\b(?:aplicad[ao]s?|utilizad[ao]s?|executad[ao]s?|rodad[ao]s?|usad[ao]s?|"
            r"usamos|aplicamos|utilizamos|executamos|rodamos|applied|executed|used)\b"
        )
        negation_re = re.compile(
            r"\b(?:n[ãa]o|sem|nunca|jamais|not|never|without|no)\b"
        )
        flagged_impeccable = False
        for sent in re.split(r"[.;!\n?]+", lower):
            if "impeccable" not in sent:
                continue
            for match in claim_verb_re.finditer(sent):
                prefix_window = sent[max(0, match.start() - 45):match.start()]
                if not negation_re.search(prefix_window):
                    errors.append(
                        "README.md appears to claim Impeccable skill was executed instead of reporting absence/install instructions."
                    )
                    flagged_impeccable = True
                    break
            if flagged_impeccable:
                break

    if check_links and repo_root is not None:
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for match in link_pattern.finditer(text):
            target = match.group(1).strip().split()[0]
            if (
                not target
                or target.startswith("#")
                or target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("mailto:")
            ):
                continue
            target_no_anchor = target.split("#", 1)[0]
            if not target_no_anchor:
                continue
            resolved = (readme_path.parent / target_no_anchor).resolve()
            if not resolved.exists():
                errors.append(f"README.md contains broken relative link: '{target}'.")

    return errors


def _scan_presentation_text(content: str, filename: str, *, include_html_quiz: bool = False) -> list[str]:
    """Scan a presentation artifact for leftover template branding, local paths, and API secrets."""
    errs: list[str] = []
    lower = content.lower()
    if "coxinh" in lower:
        errs.append(f"{filename} contains leftover 'Coxinh.IA' template branding.")

    literal_patterns = ["c:\\users\\", "c:/users/"]
    if include_html_quiz:
        literal_patterns.extend(["gabarito", "data-quiz", 'class="quiz', "class='quiz"])
    for pat in literal_patterns:
        if pat in lower:
            errs.append(f"{filename} contains forbidden pattern: '{pat}'.")

    secret_regexes = (
        ("OpenAI-style key (sk-...)", re.compile(r"(?<![a-z0-9-])sk-(?:proj-|live-|test-)?[a-z0-9]{16,}", re.I)),
        ("GitHub PAT (ghp_...)", re.compile(r"\bghp_[a-z0-9]{20,}\b", re.I)),
    )
    for label, s_re in secret_regexes:
        if s_re.search(content):
            errs.append(f"{filename} contains forbidden secret pattern: '{label}'.")
    return errs


def validate_showcase_dir(pres_dir: Path) -> list[str]:
    """Validate presentation/ deliverables against R4 and project-showcase rules."""
    errors: list[str] = []
    required_files = [
        "showcase.html",
        "showcase.config.json",
        "SOURCES.md",
        "README.md",
    ]
    for fname in required_files:
        fpath = pres_dir / fname
        if not fpath.is_file() or fpath.stat().st_size == 0:
            errors.append(f"Missing or empty presentation artifact: {fpath.name}")

    if errors:
        return errors

    # Validate showcase.config.json
    cfg_path = pres_dir / "showcase.config.json"
    cfg_text = ""
    try:
        cfg_text = cfg_path.read_text(encoding="utf-8")
        cfg = json.loads(cfg_text)
    except Exception as exc:
        errors.append(f"Invalid showcase.config.json: {exc}")
        cfg = {}

    cfg_dump = json.dumps(cfg, ensure_ascii=False).lower()
    if "coxinh" in cfg_dump:
        errors.append("showcase.config.json contains leftover 'Coxinh.IA' template branding.")
    if cfg_text:
        errors.extend(
            e for e in _scan_presentation_text(cfg_text, "showcase.config.json")
            if "Coxinh.IA" not in e
        )
    if "unidata" not in cfg_dump and "e-commerce insights" not in cfg_dump:
        errors.append("showcase.config.json does not reference Unidata / E-commerce Insights.")
    if "#0063e1" not in cfg_dump or "#000000" not in cfg_dump:
        errors.append("showcase.config.json missing Unidata design tokens (#000000 / #0063e1).")

    # Validate showcase.html
    html_path = pres_dir / "showcase.html"
    try:
        html = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return errors + [f"showcase.html invalid UTF-8: {exc}"]

    html_lower = html.lower()
    errors.extend(_scan_presentation_text(html, "showcase.html", include_html_quiz=True))

    required_sections = [
        ("1. Introdução", r"introdu[çc][ãa]o"),
        ("2. Objetivos", r"objetivos"),
        ("3. Fundamentação Teórica", r"fundamenta[çc][ãa]o\s+te[óo]rica"),
        ("4. Metodologia / Pipeline de Dados", r"metodologia"),
        ("5. Ferramentas Utilizadas", r"ferramentas\s+utilizadas"),
        ("6. Resultados Obtidos", r"resultados\s+obtidos"),
        ("7. Discussão e Limitações", r"discuss[ãa]o\s+e\s+limita[çc][õo]es"),
        ("8. Conclusão e Referências", r"conclus[ãa]o\s+e\s+refer[êe]ncias"),
    ]
    for label, pat in required_sections:
        if not re.search(pat, html_lower):
            errors.append(f"showcase.html missing required section: '{label}'.")

    if "cc by-nc-sa 4.0" not in html_lower or "olist" not in html_lower:
        errors.append("showcase.html missing Olist / CC BY-NC-SA 4.0 attribution.")

    if not any(w in html_lower for w in ("ilustrativ", "sintétic", "sintetic", "simulação", "simulacao")):
        errors.append("showcase.html lacks honest synthetic/illustrative provenance marker.")

    # Validate SOURCES.md and presentation/README.md
    try:
        sources_raw = (pres_dir / "SOURCES.md").read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return errors + [f"SOURCES.md invalid UTF-8: {exc}"]
    errors.extend(_scan_presentation_text(sources_raw, "SOURCES.md"))
    sources_text = sources_raw.lower()
    if not any(w in sources_text for w in ("implementado", "ilustrativ", "simula")):
        errors.append("SOURCES.md missing factual status matrix ('Implementado' / 'Simulação ilustrativa').")
    if "spec.md" not in sources_text or "readme.md" not in sources_text:
        errors.append("SOURCES.md missing consulted repository source references.")

    try:
        pres_readme_raw = (pres_dir / "README.md").read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return errors + [f"presentation/README.md invalid UTF-8: {exc}"]
    errors.extend(_scan_presentation_text(pres_readme_raw, "presentation/README.md"))

    return errors


def validate_zip_deliverable(
    zip_path: Path,
    *,
    expected_repo_root: Path | None = None,
) -> list[str]:
    """Audit deliverable .zip archive for CRC integrity, inclusions, exclusions, and parity."""
    errors: list[str] = []
    if not zip_path.is_file():
        return [f"Missing deliverable archive: {zip_path}"]
    if not zipfile.is_zipfile(zip_path):
        return [f"File is not a valid zip archive: {zip_path}"]

    with zipfile.ZipFile(zip_path, "r") as zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            errors.append(f"Corrupt CRC member in zip: {bad_member}")

        names = zf.namelist()
        if not names:
            return errors + ["Zip archive is empty."]

        if len(names) != len(set(names)):
            errors.append("Zip archive contains duplicate entry names.")

        for name in names:
            if "\\" in name:
                errors.append(f"Zip entry uses Windows backslash instead of POSIX '/': {name}")
            if name.startswith("/") or ".." in Path(name).parts:
                errors.append(f"Zip entry has unsafe path traversal or absolute path: {name}")

        # Strip optional single top-level directory prefix if all entries share one
        first_parts = {n.split("/", 1)[0] for n in names if "/" in n}
        all_have_slash = all("/" in n for n in names)
        prefix = ""
        if all_have_slash and len(first_parts) == 1:
            candidate = next(iter(first_parts))
            if candidate not in {"src", "tests", "data", "presentation"}:
                prefix = candidate + "/"

        norm_names = [
            n[len(prefix):] if prefix and n.startswith(prefix) else n
            for n in names
        ]
        norm_set = set(norm_names)

        # Forbidden artifact checks
        forbidden_prefixes = (
            ".venv/",
            "venv/",
            "__pycache__/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".git/",
            ".agents/",
        )
        for rel in norm_names:
            rel_lower = rel.lower()
            if any(rel_lower.startswith(fp) or f"/{fp}" in rel_lower for fp in forbidden_prefixes):
                errors.append(f"Forbidden runtime/cache/agent directory inside zip: {rel}")
            if rel_lower.startswith("data/") and rel_lower.endswith(".csv"):
                errors.append(f"Forbidden Olist CSV inside zip data/: {rel}")
            if (
                rel_lower.endswith(".csv")
                and not rel_lower.startswith("tests/")
                and ("olist_" in rel_lower or "product_category_name_translation" in rel_lower)
            ):
                errors.append(f"Forbidden Olist CSV inside zip: {rel}")
            if rel_lower.endswith(".zip"):
                errors.append(f"Nested zip archive found inside zip: {rel}")

        # Required deliverable files
        required_members = [
            ".gitignore",
            "requirements.txt",
            "README.md",
            "app.py",
            "data/.gitkeep",
            "src/unidata/__init__.py",
            "src/unidata/config.py",
            "src/unidata/loader.py",
            "src/unidata/pipeline.py",
            "src/unidata/analytics.py",
            "src/unidata/segmentation.py",
            "src/unidata/recommendations.py",
            "presentation/showcase.html",
            "presentation/showcase.config.json",
            "presentation/SOURCES.md",
            "presentation/README.md",
        ]
        for req in required_members:
            if req not in norm_set:
                errors.append(f"Missing required member in zip: {req}")

        if not any(n.startswith("tests/") and n.endswith(".py") for n in norm_names):
            errors.append("Missing automated tests under tests/ inside zip.")

        if expected_repo_root is not None:
            ignored_parts = {
                ".venv",
                "venv",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                ".git",
                ".agents",
            }
            parity_candidates: list[Path] = []
            for root_rel in (".gitignore", "requirements.txt", "README.md", "app.py", "data/.gitkeep"):
                candidate_file = expected_repo_root / root_rel
                if candidate_file.is_file():
                    parity_candidates.append(candidate_file)
            for subdir in ("src", "tests", "presentation"):
                sub_path = expected_repo_root / subdir
                if sub_path.is_dir():
                    for p in sorted(sub_path.rglob("*")):
                        if not p.is_file():
                            continue
                        rel_parts = p.relative_to(expected_repo_root).parts
                        if any(part in ignored_parts for part in rel_parts):
                            continue
                        if p.suffix.lower() in {".pyc", ".pyo", ".zip"}:
                            continue
                        if rel_parts[0] == "data" and p.suffix.lower() == ".csv":
                            continue
                        parity_candidates.append(p)

            for ws_file in parity_candidates:
                rel = ws_file.relative_to(expected_repo_root).as_posix()
                arc_name = f"{prefix}{rel}" if prefix else rel
                if rel not in norm_set or arc_name not in names:
                    errors.append(f"Missing workspace file in zip: {rel}")
                    continue
                ws_bytes = ws_file.read_bytes()
                zip_info = zf.getinfo(arc_name)
                zip_bytes = zf.read(arc_name)
                if (
                    zip_info.file_size != len(ws_bytes)
                    or hashlib.sha256(zip_bytes).hexdigest() != hashlib.sha256(ws_bytes).hexdigest()
                ):
                    errors.append(
                        f"Zip member '{rel}' differs from workspace file (stale zip)."
                    )

    return errors


def build_synthetic_readme(
    target_path: Path,
    *,
    include_title: bool = True,
    include_license: bool = True,
    claim_impeccable_executed: bool = False,
) -> Path:
    """Create a synthetic README.md for always-on validator testing."""
    parts = []
    if include_title:
        parts.append("# Unidata\n")
    else:
        parts.append("# E-commerce Dashboard\n")
    parts.append(
        "## Resumo e Problema\n"
        "Painel analítico E-commerce Insights para consolidar pedidos da Olist.\n\n"
        "## Arquitetura e Fluxo\n"
        "Fluxo modular: `loader.py` -> `pipeline.py` -> `analytics.py` -> "
        "`segmentation.py` -> `recommendations.py` -> `app.py`.\n\n"
        "## Instalação e Execução\n"
        "```bash\npip install -r requirements.txt\n"
        "streamlit run app.py\npytest\n```\n"
        "Baixe em https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
        "e coloque em `data/` os arquivos:\n"
        "- `olist_orders_dataset.csv`\n- `olist_order_items_dataset.csv`\n"
        "- `olist_customers_dataset.csv`\n- `olist_products_dataset.csv`\n"
        "- `product_category_name_translation.csv`\n\n"
        "## Metodologia e Limitações\n"
        "K-means com `k=4`, `random_state=42`, `n_init=10`. "
        "Padrão histórico sem inferência causal ou previsão.\n\n"
    )
    if claim_impeccable_executed:
        parts.append("A skill Impeccable foi executada localmente.\n\n")
    else:
        parts.append(
            "Skill Impeccable não estava instalada localmente; "
            "para ativar, instale a skill Impeccable no agente compatível.\n\n"
        )
    if include_license:
        parts.append(
            "## Licença\nDados Olist sob licença CC BY-NC-SA 4.0 (uso não comercial).\n"
        )
    target_path.write_text("".join(parts), encoding="utf-8")
    return target_path


def build_synthetic_showcase(
    pres_dir: Path,
    *,
    include_section_8: bool = True,
    leak_coxinha: bool = False,
) -> Path:
    """Create a synthetic presentation/ folder for always-on validator testing."""
    pres_dir.mkdir(parents=True, exist_ok=True)
    brand = "Coxinh.IA" if leak_coxinha else "Unidata — E-commerce Insights"
    (pres_dir / "showcase.config.json").write_text(
        json.dumps(
            {
                "title": brand,
                "theme": {"canvas": "#000000", "accent": "#0063e1"},
            }
        ),
        encoding="utf-8",
    )
    sections = [
        "1. Introdução",
        "2. Objetivos",
        "3. Fundamentação Teórica",
        "4. Metodologia / Pipeline de Dados",
        "5. Ferramentas Utilizadas",
        "6. Resultados Obtidos",
        "7. Discussão e Limitações",
    ]
    if include_section_8:
        sections.append("8. Conclusão e Referências")

    html_sections = "\n".join(f"<section><h2>{s}</h2></section>" for s in sections)
    (pres_dir / "showcase.html").write_text(
        f"<!doctype html><html lang='pt-BR'><head><title>{brand}</title></head>"
        f"<body>{html_sections}<p>Base Olist CC BY-NC-SA 4.0 — Simulação ilustrativa.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    (pres_dir / "SOURCES.md").write_text(
        "# Fontes\nData: 2026-11-25\n- `spec.md` — Implementado\n- `README.md` — Implementado\n"
        "- Demo — Simulação ilustrativa\n",
        encoding="utf-8",
    )
    (pres_dir / "README.md").write_text("# Apresentação Unidata\n", encoding="utf-8")
    return pres_dir


def build_synthetic_zip(
    zip_path: Path,
    *,
    include_olist_csv: bool = False,
    include_venv: bool = False,
    include_agents: bool = False,
    omit_readme: bool = False,
    omit_showcase: bool = False,
) -> Path:
    """Create a synthetic deliverable .zip for always-on zip-audit validator testing."""
    files: dict[str, bytes] = {
        ".gitignore": b"data/*\n!data/.gitkeep\n.venv/\n*.zip\n",
        "requirements.txt": b"pandas==3.1.1\n",
        "app.py": b"# app\n",
        "data/.gitkeep": b"",
        "src/unidata/__init__.py": b"",
        "src/unidata/config.py": b"",
        "src/unidata/loader.py": b"",
        "src/unidata/pipeline.py": b"",
        "src/unidata/analytics.py": b"",
        "src/unidata/segmentation.py": b"",
        "src/unidata/recommendations.py": b"",
        "tests/test_smoke.py": b"def test_ok(): assert True\n",
        "presentation/showcase.config.json": b"{}",
        "presentation/SOURCES.md": b"# Sources\n",
        "presentation/README.md": b"# Pres\n",
    }
    if not omit_readme:
        files["README.md"] = b"# Unidata\n"
    if not omit_showcase:
        files["presentation/showcase.html"] = b"<html></html>"
    if include_olist_csv:
        files["data/olist_orders_dataset.csv"] = b"order_id\n1\n"
    if include_venv:
        files[".venv/pyvenv.cfg"] = b"home = C:\\Python313\n"
    if include_agents:
        files[".agents/teamwork/meta.md"] = b"secret\n"

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files.items():
            zf.writestr(arcname, data)
    return zip_path
