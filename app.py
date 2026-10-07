
import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
import json
import base64
from datetime import datetime, date
from pathlib import Path

DB_PATH = "mcn_data.db"

st.set_page_config(
    page_title="SINGO MCN Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================
# DATABASE
# =========================
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT '',
            creator_id TEXT DEFAULT '',
            pic TEXT DEFAULT '',
            share_percent REAL DEFAULT 0,
            status TEXT DEFAULT 'Đang hoạt động',
            joined_date TEXT DEFAULT '',
            note TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            uploaded_at TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            period_start TEXT DEFAULT '',
            period_end TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            username TEXT,
            nickname TEXT,
            video_id TEXT,
            link TEXT,
            title TEXT,
            post_time TEXT,
            duration_sec REAL DEFAULT 0,
            gmv REAL DEFAULT 0,
            units REAL DEFAULT 0,
            creator_commission REAL DEFAULT 0,
            direct_gmv REAL DEFAULT 0,
            gpm REAL DEFAULT 0,
            views REAL DEFAULT 0,
            completion_rate REAL DEFAULT 0,
            product_id TEXT,
            likes REAL DEFAULT 0,
            comments REAL DEFAULT 0,
            shares REAL DEFAULT 0,
            ctr REAL DEFAULT 0,
            ctor REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS overview_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            period_start TEXT DEFAULT '',
            period_end TEXT DEFAULT '',
            followers REAL DEFAULT 0,
            gmv REAL DEFAULT 0,
            orders REAL DEFAULT 0,
            live_gmv REAL DEFAULT 0,
            video_gmv REAL DEFAULT 0,
            live_orders REAL DEFAULT 0,
            video_orders REAL DEFAULT 0,
            live_ctr REAL DEFAULT 0,
            video_ctr REAL DEFAULT 0,
            direct_gmv REAL DEFAULT 0,
            direct_live_gmv REAL DEFAULT 0,
            direct_video_gmv REAL DEFAULT 0,
            direct_orders REAL DEFAULT 0,
            sales_units REAL DEFAULT 0,
            live_sales_units REAL DEFAULT 0,
            video_sales_units REAL DEFAULT 0,
            creator_sales_units REAL DEFAULT 0,
            creator_commission REAL DEFAULT 0,
            commission_base REAL DEFAULT 0,
            live_views REAL DEFAULT 0,
            views REAL DEFAULT 0,
            live_sessions REAL DEFAULT 0,
            videos REAL DEFAULT 0,
            affiliate_gmv REAL DEFAULT 0,
            affiliate_orders REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS live_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            username TEXT,
            nickname TEXT,
            live_id TEXT,
            live_title TEXT,
            start_time TEXT,
            gmv REAL DEFAULT 0,
            direct_gmv REAL DEFAULT 0,
            units REAL DEFAULT 0,
            viewers REAL DEFAULT 0,
            gpm REAL DEFAULT 0,
            click_rate REAL DEFAULT 0,
            sku_orders REAL DEFAULT 0,
            customers REAL DEFAULT 0,
            duration_sec REAL DEFAULT 0,
            views REAL DEFAULT 0,
            comments REAL DEFAULT 0,
            shares REAL DEFAULT 0,
            likes REAL DEFAULT 0,
            avg_price REAL DEFAULT 0,
            ctor REAL DEFAULT 0,
            avg_watch_sec REAL DEFAULT 0,
            new_followers REAL DEFAULT 0,
            products REAL DEFAULT 0,
            impressions REAL DEFAULT 0,
            product_clicks REAL DEFAULT 0,
            ctr REAL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    conn.commit()
    conn.close()

if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = get_setting("theme_mode", "🌓 Theo hệ thống")
if "mcn_bg_css" not in st.session_state:
    st.session_state["mcn_bg_css"] = get_setting("mcn_bg_css", "")

# =========================
# HELPERS
# =========================
def clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def money_to_float(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "--", "-"}:
        return 0.0
    # TikTok Excel exports may contain strings such as 1.802.371.690₫.
    # Keep only the numeric part and treat dots as thousand separators.
    s = s.replace("₫", "").replace("đ", "").replace("Đ", "")
    s = s.replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s:
        return 0.0
    # Vietnamese/TikTok currency format: 1.802.371.690 -> 1802371690
    if s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s:
        left, right = s.split(".", 1)
        if len(right) == 3:
            s = left + right
    try:
        return float(s)
    except Exception:
        return 0.0

def num_to_float(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "--", "-"}:
        return 0.0
    s = s.replace("%", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return 0.0

def duration_to_seconds(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip().lower()
    if not s:
        return 0.0

    # 4h16min52s
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)min)?(?:(\d+)s)?", s)
    if m and any(g is not None for g in m.groups()):
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        sec = int(m.group(3) or 0)
        return h * 3600 + mi * 60 + sec

    # 44s / 36s
    m = re.fullmatch(r"(?:(\d+)m)?(?:(\d+)s)?", s)
    if m and any(g is not None for g in m.groups()):
        mi = int(m.group(1) or 0)
        sec = int(m.group(2) or 0)
        return mi * 60 + sec

    return 0.0

def seconds_to_hms(sec):
    sec = int(sec or 0)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"

def parse_video_date(x):
    if pd.isna(x):
        return pd.NaT
    return pd.to_datetime(str(x).strip(), errors="coerce")

def parse_live_start(x):
    if pd.isna(x):
        return pd.NaT
    s = str(x).strip()
    # 08:38:00 17/02/2026 - 12:54:52 17/02/2026
    first = s.split(" - ")[0].strip()
    return pd.to_datetime(first, format="%H:%M:%S %d/%m/%Y", errors="coerce")

def file_hash(data):
    return hashlib.sha256(data).hexdigest()

def fmt_money(x):
    return f"{x:,.0f} ₫".replace(",", ".")

def fmt_number(x):
    return f"{x:,.0f}".replace(",", ".")

def get_creators():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM creators ORDER BY username", conn)
    conn.close()
    return df

def get_creator_map():
    df = get_creators()
    if df.empty:
        return {}
    return {
        normalize_creator_key(r["username"]): float(r["share_percent"] or 0)
        for _, r in df.iterrows()
    }

def normalize_username(x):
    return clean_text(x).lstrip("@").lower()

def normalize_creator_key(x):
    """Chuẩn hóa username để đối chiếu Creator giữa DATA CREATOR và file TikTok."""
    s = clean_text(x).lstrip("@").strip().lower()
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def upload_exists(filehash):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, source, file_name FROM uploads WHERE file_hash = ?",
        (filehash,)
    ).fetchone()
    conn.close()
    return row

def save_upload(source, file_name, filehash, row_count, period_start="", period_end=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO uploads
        (source, file_name, file_hash, uploaded_at, row_count, period_start, period_end)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        source, file_name, filehash, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        int(row_count), str(period_start), str(period_end)
    ))
    upload_id = cur.lastrowid
    conn.commit()
    conn.close()
    return upload_id

def delete_upload(upload_id):
    conn = get_conn()
    conn.execute("DELETE FROM overview_data WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM video_data WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM live_data WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
    conn.commit()
    conn.close()

def load_uploads():
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM uploads ORDER BY uploaded_at DESC", conn
    )
    conn.close()
    return df

# =========================
# IMPORT OVERVIEW / MONTHLY CREATOR REPORT
# =========================
def extract_period_from_overview(df, file_name=""):
    # 1) Ưu tiên lấy kỳ ngay từ tên file TikTok, ví dụ:
    # CustomReport_Creator 2026-09-01_2026-09-30.xlsx
    name = str(file_name or "")
    m_file = re.search(r"(\d{4}-\d{2}-\d{2})[_-](\d{4}-\d{2}-\d{2})", name)
    if m_file:
        return m_file.group(1), m_file.group(2)

    if "Ngày" not in df.columns:
        return "", ""

    valid = df.copy()
    if "Tên người dùng của nhà sáng tạo" in valid.columns:
        valid = valid[valid["Tên người dùng của nhà sáng tạo"].astype(str).str.strip().ne("")]

    vals = valid["Ngày"].astype(str).str.strip()
    vals = vals[~vals.str.lower().isin(["", "--", "nan", "none", "tóm tắt", "-"])]
    if vals.empty:
        return "", ""

    # 2) Tìm mọi chuỗi YYYY-MM-DD trong cột Ngày. Cách này chịu được
    # các định dạng TikTok khác nhau như 2026-09-01-2026-09-30,
    # 2026-09-01 ~ 2026-09-30 hoặc có thêm chữ.
    found = []
    for value in vals.tolist():
        found.extend(re.findall(r"\d{4}-\d{2}-\d{2}", value))
    if found:
        dates = pd.to_datetime(pd.Series(found), errors="coerce").dropna()
        if not dates.empty:
            return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")

    # 3) Fallback cuối cùng: pandas parse trực tiếp.
    dates = pd.to_datetime(vals, errors="coerce").dropna()
    if not dates.empty:
        return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")
    return "", ""

def process_overview_upload(raw_bytes, file_name):
    """
    Tổng quan lấy dữ liệu trực tiếp theo TÊN CỘT của file TikTok.
    Đặc biệt:
      - 'Hoa hồng ước tính' = hoa hồng ước tính của NST (cột W)
      - Hoa hồng MCN = Hoa hồng NST * % MCN
    Không map theo vị trí cột để tránh lệch dữ liệu khi TikTok thay đổi thứ tự cột.
    """
    try:
        df = pd.read_excel(
            io.BytesIO(raw_bytes),
            sheet_name="Báo cáo tùy chỉnh"
        )
    except Exception as e:
        st.error(f"Không đọc được file Tổng quan: {e}")
        return

    required = [
        "Tên người dùng của nhà sáng tạo",
        "GMV nhờ nhà sáng tạo",
        "Hoa hồng ước tính",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("File Tổng quan thiếu cột: " + ", ".join(missing))
        return

    # Chuẩn hóa username và bỏ dòng tổng / dòng không phải Creator.
    df["__username"] = df["Tên người dùng của nhà sáng tạo"].apply(normalize_username)
    df = df[
        df["__username"].ne("")
        & ~df["__username"].isin({"-", "tóm tắt", "tong", "tổng"})
    ].copy()

    if df.empty:
        st.warning("Không có dòng Creator hợp lệ trong file Tổng quan.")
        return

    # Kỳ dữ liệu: ưu tiên ngày trong tên file, sau đó mới dùng cột Ngày.
    period_start, period_end = extract_period_from_overview(df, file_name)

    # Build dữ liệu bằng TÊN CỘT, tuyệt đối không dựa vào index cột.
    source_map = {
        "followers": ("Số người theo dõi của nhà sáng tạo", "num"),
        "gmv": ("GMV nhờ nhà sáng tạo", "money"),
        "orders": ("Đơn hàng nhờ nhà sáng tạo", "num"),
        "live_gmv": ("GMV nhờ buổi LIVE của nhà sáng tạo", "money"),
        "video_gmv": ("GMV đến từ video liên kết", "money"),
        "live_orders": ("Đơn hàng nhờ buổi LIVE của nhà sáng tạo", "num"),
        "video_orders": ("Đơn hàng nhờ video của nhà sáng tạo", "num"),
        "live_ctr": ("CTR LIVE", "num"),
        "video_ctr": ("CTR video", "num"),
        "direct_gmv": ("GMV trực tiếp", "money"),
        "direct_live_gmv": ("GMV trực tiếp từ LIVE", "money"),
        "direct_video_gmv": ("GMV trực tiếp từ video", "money"),
        "direct_orders": ("Đơn hàng trực tiếp", "num"),
        "sales_units": ("Lượt bán", "num"),
        "live_sales_units": ("Số món bán ra từ buổi LIVE của nhà sáng tạo", "num"),
        "video_sales_units": ("số món bán ra từ video của nhà sáng tạo", "num"),
        "creator_sales_units": ("Số món bán ra nhờ nhà sáng tạo", "num"),

        # QUAN TRỌNG: đây chính là cột W trong file hiện tại.
        "creator_commission": ("Hoa hồng ước tính", "money"),

        "commission_base": ("Giá trị cơ sở tính hoa hồng", "money"),
        "live_views": ("Lượt xem LIVE", "num"),
        "views": ("Lượt xem", "num"),
        "live_sessions": ("Buổi LIVE", "num"),
        "videos": ("Video", "num"),
        "affiliate_gmv": ("GMV nhờ nhà sáng tạo đối tác liên kết", "money"),
        "affiliate_orders": ("Đơn hàng nhờ nhà sáng tạo đối tác liên kết", "num"),
    }

    def read_metric(row, spec):
        col, kind = spec
        value = row.get(col, 0)
        return money_to_float(value) if kind == "money" else num_to_float(value)

    rows = []
    for _, r in df.iterrows():
        row = {
            "username": r["__username"],
            "period_start": str(period_start or ""),
            "period_end": str(period_end or ""),
        }
        for db_col, spec in source_map.items():
            row[db_col] = read_metric(r, spec)
        rows.append(row)

    # Nếu đã có dữ liệu Tổng quan cho đúng kỳ, xóa bản cũ và lưu lại
    # bản mới. Điều này cho phép sửa/re-import cùng một tháng.
    conn = get_conn()
    try:
        cur = conn.cursor()

        old_uploads = cur.execute("""
            SELECT id
            FROM uploads
            WHERE source = 'Overview'
              AND period_start = ?
              AND period_end = ?
        """, (str(period_start or ""), str(period_end or ""))).fetchall()

        for (old_id,) in old_uploads:
            cur.execute("DELETE FROM overview_data WHERE upload_id = ?", (old_id,))
            cur.execute("DELETE FROM uploads WHERE id = ?", (old_id,))

        cur.execute("""
            INSERT INTO uploads
            (source, file_name, file_hash, uploaded_at, row_count, period_start, period_end)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "Overview",
            file_name,
            file_hash(raw_bytes),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            len(rows),
            str(period_start or ""),
            str(period_end or ""),
        ))
        upload_id = cur.lastrowid

        columns = [
            "upload_id", "username", "period_start", "period_end",
            "followers", "gmv", "orders", "live_gmv", "video_gmv",
            "live_orders", "video_orders", "live_ctr", "video_ctr",
            "direct_gmv", "direct_live_gmv", "direct_video_gmv",
            "direct_orders", "sales_units", "live_sales_units",
            "video_sales_units", "creator_sales_units", "creator_commission",
            "commission_base", "live_views", "views", "live_sessions",
            "videos", "affiliate_gmv", "affiliate_orders"
        ]

        placeholders = ",".join(["?"] * len(columns))
        sql = f"""
            INSERT INTO overview_data ({",".join(columns)})
            VALUES ({placeholders})
        """

        values = []
        for r in rows:
            values.append((
                upload_id,
                r["username"],
                r["period_start"],
                r["period_end"],
                r["followers"],
                r["gmv"],
                r["orders"],
                r["live_gmv"],
                r["video_gmv"],
                r["live_orders"],
                r["video_orders"],
                r["live_ctr"],
                r["video_ctr"],
                r["direct_gmv"],
                r["direct_live_gmv"],
                r["direct_video_gmv"],
                r["direct_orders"],
                r["sales_units"],
                r["live_sales_units"],
                r["video_sales_units"],
                r["creator_sales_units"],
                r["creator_commission"],
                r["commission_base"],
                r["live_views"],
                r["views"],
                r["live_sessions"],
                r["videos"],
                r["affiliate_gmv"],
                r["affiliate_orders"],
            ))

        cur.executemany(sql, values)

        # Kiểm tra ngay sau khi insert: giá trị W của Creator mẫu phải
        # được lưu đúng vào creator_commission.
        check = cur.execute("""
            SELECT username, creator_commission
            FROM overview_data
            WHERE upload_id = ?
            ORDER BY id
            LIMIT 1
        """, (upload_id,)).fetchone()

        if check is None:
            raise ValueError("Không tạo được dữ liệu Tổng quan sau khi lưu.")

        conn.commit()

    except Exception as e:
        conn.rollback()
        st.error(f"Không thể lưu dữ liệu Tổng quan: {e}")
        return
    finally:
        conn.close()

    st.success(
        f"Đã lưu file Tổng quan: {file_name} · "
        f"{len(rows):,} Creator · kỳ {period_start or '?'} → {period_end or '?'}"
    )

    st.info(
        "Đã lấy đúng cột 'Hoa hồng ước tính' của file làm hoa hồng NST. "
        "Hoa hồng MCN sẽ được tính theo % MCN trong DATA CREATOR."
    )

# =========================
# IMPORT VIDEO
# =========================
def process_video_upload(raw_bytes, file_name):
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes), low_memory=False)
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig", low_memory=False)
        except Exception as e:
            st.error(f"Không đọc được file Video: {e}")
            return

    required = [
        "Tên người dùng của nhà sáng tạo",
        "GMV nhờ nhà sáng tạo",
        "Hoa hồng ước tính",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("File Video thiếu cột: " + ", ".join(missing))
        return

    # TikTok export puts descriptions in the first row. Remove rows without username.
    df["__username"] = df["Tên người dùng của nhà sáng tạo"].apply(normalize_username)
    df = df[df["__username"] != ""].copy()

    if df.empty:
        st.warning("Không có dòng dữ liệu Creator hợp lệ trong file.")
        return

    h = file_hash(raw_bytes)
    old = upload_exists(h)
    if old:
        st.warning(f"File này đã được upload trước đó: {old[2]}")
        return

    df["__date"] = df["Thời gian đăng"].apply(parse_video_date) if "Thời gian đăng" in df.columns else pd.NaT
    period_start = df["__date"].min()
    period_end = df["__date"].max()

    upload_id = save_upload(
        "Video", file_name, h, len(df),
        period_start.strftime("%Y-%m-%d") if pd.notna(period_start) else "",
        period_end.strftime("%Y-%m-%d") if pd.notna(period_end) else ""
    )

    creator_map = get_creator_map()
    rows = []

    for _, r in df.iterrows():
        username = r["__username"]
        commission = money_to_float(r.get("Hoa hồng ước tính", 0))
        share = creator_map.get(normalize_creator_key(username), 0)
        # MCN actual commission = Creator commission (W) x MCN share %
        mcn_commission = commission * share / 100.0

        rows.append((
            upload_id,
            username,
            clean_text(r.get("Biệt danh của nhà sáng tạo")),
            clean_text(r.get("ID video")),
            clean_text(r.get("Liên kết")),
            clean_text(r.get("Tên video")),
            str(r.get("Thời gian đăng", "")),
            duration_to_seconds(r.get("Thời lượng")),
            money_to_float(r.get("GMV nhờ nhà sáng tạo")),
            num_to_float(r.get("Số món bán ra nhờ nhà sáng tạo")),
            commission,
            money_to_float(r.get("GMV trực tiếp")),
            money_to_float(r.get("GPM video")),
            num_to_float(r.get("Lượt xem")),
            num_to_float(r.get("Tỷ lệ xem hết")),
            clean_text(r.get("ID sản phẩm")),
            num_to_float(r.get("Lượt thích")),
            num_to_float(r.get("Lượt bình luận")),
            num_to_float(r.get("Lượt chia sẻ")),
            num_to_float(r.get("CTR")),
            num_to_float(r.get("CTOR (đơn hàng SKU) (video)")),
        ))

    conn = get_conn()
    conn.executemany("""
        INSERT INTO video_data (
            upload_id, username, nickname, video_id, link, title, post_time,
            duration_sec, gmv, units, creator_commission, direct_gmv, gpm,
            views, completion_rate, product_id, likes, comments, shares, ctr, ctor
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()

    st.success(f"Đã lưu {len(rows):,} dòng Video từ {file_name}.")
    st.info(
        "Lưu ý: % MCN được lấy theo DATA CREATOR tại thời điểm upload. "
        "Nếu sau này đổi % MCN của Creator, dữ liệu đã lưu không tự tính lại."
    )

# =========================
# IMPORT LIVE
# =========================
def process_live_upload(raw_bytes, file_name):
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes), low_memory=False)
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig", low_memory=False)
        except Exception as e:
            st.error(f"Không đọc được file Live: {e}")
            return

    required = [
        "Tên người dùng của nhà sáng tạo",
        "GMV nhờ nhà sáng tạo",
        "Thời gian bắt đầu",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("File Live thiếu cột: " + ", ".join(missing))
        return

    df["__username"] = df["Tên người dùng của nhà sáng tạo"].apply(normalize_username)
    df = df[df["__username"] != ""].copy()

    if df.empty:
        st.warning("Không có dòng dữ liệu Creator hợp lệ trong file.")
        return

    h = file_hash(raw_bytes)
    old = upload_exists(h)
    if old:
        st.warning(f"File này đã được upload trước đó: {old[2]}")
        return

    df["__date"] = df["Thời gian bắt đầu"].apply(parse_live_start)
    period_start = df["__date"].min()
    period_end = df["__date"].max()

    upload_id = save_upload(
        "Live", file_name, h, len(df),
        period_start.strftime("%Y-%m-%d") if pd.notna(period_start) else "",
        period_end.strftime("%Y-%m-%d") if pd.notna(period_end) else ""
    )

    rows = []
    for _, r in df.iterrows():
        rows.append((
            upload_id,
            r["__username"],
            clean_text(r.get("Biệt danh của nhà sáng tạo")),
            clean_text(r.get("ID LIVE")),
            clean_text(r.get("LIVE")),
            str(r.get("Thời gian bắt đầu", "")),
            money_to_float(r.get("GMV nhờ nhà sáng tạo")),
            money_to_float(r.get("GMV trực tiếp")),
            num_to_float(r.get("Số món bán ra nhờ nhà sáng tạo")),
            num_to_float(r.get("Người xem")),
            money_to_float(r.get("GPM hiển thị")),
            num_to_float(r.get("Tỷ lệ nhấn")),
            num_to_float(r.get("Đơn hàng SKU từ nhà sáng tạo")),
            num_to_float(r.get("Khách hàng")),
            duration_to_seconds(r.get("Thời lượng")),
            num_to_float(r.get("Lượt xem")),
            num_to_float(r.get("Lượt bình luận")),
            num_to_float(r.get("Lượt chia sẻ")),
            num_to_float(r.get("Lượt thích")),
            money_to_float(r.get("Giá trung bình")),
            num_to_float(r.get("CTOR LIVE liên kết (đơn hàng SKU)")),
            duration_to_seconds(r.get("Thời lượng xem trung bình")),
            num_to_float(r.get("Người theo dõi mới")),
            num_to_float(r.get("Sản phẩm")),
            num_to_float(r.get("Lượt hiển thị sản phẩm")),
            num_to_float(r.get("Lượt nhấp vào sản phẩm")),
            num_to_float(r.get("CTR")),
        ))

    conn = get_conn()
    conn.executemany("""
        INSERT INTO live_data (
            upload_id, username, nickname, live_id, live_title, start_time,
            gmv, direct_gmv, units, viewers, gpm, click_rate, sku_orders,
            customers, duration_sec, views, comments, shares, likes, avg_price,
            ctor, avg_watch_sec, new_followers, products, impressions,
            product_clicks, ctr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()

    st.success(f"Đã lưu {len(rows):,} dòng Live từ {file_name}.")
    st.warning(
        "File Live hiện tại không có cột 'Hoa hồng ước tính', nên app không tự tính "
        "hoa hồng thực tế MCN cho Live. Các KPI Live vẫn được lưu và phân tích đầy đủ."
    )

# =========================
# DATA CREATOR
# =========================
def render_creators():
    st.title("👥 DATA CREATOR")
    st.caption("Quản lý Creator trong Net và % hoa hồng MCN được hưởng.")

    tab1, tab2 = st.tabs(["➕ Thêm Creator", "📋 Danh sách Creator"])

    with tab1:
        with st.form("creator_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                username = st.text_input("Username TikTok *", placeholder="vd: minhnguyet.beauty")
                display_name = st.text_input("Tên / Biệt danh")
            with c2:
                creator_id = st.text_input("Creator ID")
                pic = st.text_input("PIC")
            with c3:
                share = st.number_input("% MCN được hưởng *", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
                status = st.selectbox("Trạng thái", ["Đang hoạt động", "Tạm ngưng", "Đã rời Net"])
            joined = st.date_input("Ngày vào Net", value=date.today())
            note = st.text_area("Ghi chú")

            submitted = st.form_submit_button("💾 Lưu Creator", use_container_width=True)

        if submitted:
            username_clean = normalize_username(username)
            if not username_clean:
                st.error("Vui lòng nhập Username.")
            else:
                conn = get_conn()
                try:
                    conn.execute("""
                        INSERT INTO creators
                        (username, display_name, creator_id, pic, share_percent, status, joined_date, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        username_clean, display_name.strip(), creator_id.strip(), pic.strip(),
                        float(share), status, str(joined), note.strip()
                    ))
                    conn.commit()
                    st.success(f"Đã thêm @{username_clean}")
                except sqlite3.IntegrityError:
                    st.error("Username này đã tồn tại trong DATA CREATOR.")
                finally:
                    conn.close()

        st.divider()
        st.markdown("### 📥 Import nhiều Creator")
        template = pd.DataFrame([{
            "Username": "",
            "Tên / Biệt danh": "",
            "Creator ID": "",
            "PIC": "",
            "% MCN": 20,
            "Trạng thái": "Đang hoạt động",
            "Ngày vào Net": "",
            "Ghi chú": ""
        }])
        st.download_button(
            "⬇️ Tải file mẫu Creator",
            template.to_csv(index=False).encode("utf-8-sig"),
            "mau_data_creator.csv",
            "text/csv"
        )

        bulk = st.file_uploader("Upload Excel/CSV Creator", type=["xlsx", "xls", "csv"], key="creator_bulk")
        if bulk:
            try:
                if bulk.name.lower().endswith(".csv"):
                    bdf = pd.read_csv(bulk)
                else:
                    bdf = pd.read_excel(bulk)
                st.dataframe(bdf.head(10), use_container_width=True)
                if st.button("📥 Lưu toàn bộ Creator", key="save_bulk_creator"):
                    conn = get_conn()
                    ok, skip = 0, 0
                    for _, r in bdf.iterrows():
                        u = normalize_username(r.get("Username", ""))
                        if not u:
                            skip += 1
                            continue
                        try:
                            conn.execute("""
                                INSERT INTO creators
                                (username, display_name, creator_id, pic, share_percent, status, joined_date, note)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                u,
                                clean_text(r.get("Tên / Biệt danh")),
                                clean_text(r.get("Creator ID")),
                                clean_text(r.get("PIC")),
                                num_to_float(r.get("% MCN", 0)),
                                clean_text(r.get("Trạng thái")) or "Đang hoạt động",
                                clean_text(r.get("Ngày vào Net")),
                                clean_text(r.get("Ghi chú")),
                            ))
                            ok += 1
                        except sqlite3.IntegrityError:
                            skip += 1
                    conn.commit()
                    conn.close()
                    st.success(f"Đã thêm {ok} Creator. Bỏ qua {skip} dòng trùng/thiếu Username.")
            except Exception as e:
                st.error(f"Không đọc được file Creator: {e}")

    with tab2:
        df = get_creators()
        if df.empty:
            st.info("Chưa có Creator. Hãy thêm Creator ở tab đầu tiên.")
            return

        search = st.text_input("🔎 Tìm Username / tên Creator", key="creator_search")
        if search:
            s = search.lower().strip()
            df = df[
                df["username"].str.lower().str.contains(s, na=False)
                | df["display_name"].str.lower().str.contains(s, na=False)
            ]

        display = df[[
            "username", "display_name", "creator_id", "pic",
            "share_percent", "status", "joined_date", "note"
        ]].copy()
        display.columns = [
            "Username", "Tên / Biệt danh", "Creator ID", "PIC",
            "% MCN", "Trạng thái", "Ngày vào Net", "Ghi chú"
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)

        st.markdown("### ✏️ Chỉnh % MCN nhanh")
        selected = st.selectbox(
            "Chọn Creator",
            df["username"].tolist(),
            format_func=lambda x: "@" + x
        )
        current = float(df.loc[df["username"] == selected, "share_percent"].iloc[0])
        new_share = st.number_input("% MCN mới", 0.0, 100.0, current, 0.5, key="new_share")

        if st.button("💾 Cập nhật % MCN"):
            conn = get_conn()
            conn.execute("UPDATE creators SET share_percent = ? WHERE username = ?", (new_share, selected))
            conn.commit()
            conn.close()
            st.success(f"Đã cập nhật @{selected} = {new_share:g}%")
            st.rerun()

        st.markdown("### 🗑️ Xóa Creator")
        st.caption("Xóa Creator khỏi DATA CREATOR. Dữ liệu Live/Video/Tổng quan đã lưu không bị xóa.")
        delete_creator = st.selectbox(
            "Chọn Creator cần xóa",
            df["username"].tolist(),
            format_func=lambda x: "@" + x,
            key="delete_creator_select"
        )
        confirm_delete = st.checkbox(
            f"Tôi chắc chắn muốn xóa @{delete_creator}",
            key="confirm_delete_creator"
        )
        if st.button("🗑️ Xóa Creator", type="secondary", disabled=not confirm_delete):
            conn = get_conn()
            conn.execute("DELETE FROM creators WHERE username = ?", (delete_creator,))
            conn.commit()
            conn.close()
            st.success(f"Đã xóa @{delete_creator} khỏi DATA CREATOR.")
            st.rerun()

def get_active_creator_keys():
    creators = get_creators()
    if creators.empty:
        return {}
    active = creators[creators["share_percent"].astype(float) > 0]
    return {
        normalize_creator_key(r["username"]): {
            "username": r["username"],
            "share_percent": float(r["share_percent"] or 0),
        }
        for _, r in active.iterrows()
    }

# =========================
# LIVE ANALYTICS
# =========================
def render_live():
    st.title("🔴 LIVE ANALYTICS")
    st.caption("Chỉ hiển thị Creator trong Net có % MCN > 0. Dữ liệu được lưu cộng dồn theo từng file.")

    uploaded = st.file_uploader(
        "📤 Upload file Live mới",
        type=["csv"],
        key="live_upload"
    )
    if uploaded:
        if st.button("🚀 Lưu dữ liệu Live", key="save_live"):
            process_live_upload(uploaded.getvalue(), uploaded.name)

    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT l.*, u.file_name, u.period_start, u.period_end
        FROM live_data l
        JOIN uploads u ON l.upload_id = u.id
    """, conn)
    conn.close()

    if df.empty:
        st.info("Chưa có dữ liệu Live. Upload file Live ở phía trên.")
        return

    df["date"] = pd.to_datetime(df["start_time"], errors="coerce")
    creators = sorted([x for x in df["username"].dropna().unique() if x])

    c1, c2, c3 = st.columns(3)
    with c1:
        creator_filter = st.multiselect("Creator", creators)
    with c2:
        date_min = df["date"].min().date() if df["date"].notna().any() else date.today()
        date_max = df["date"].max().date() if df["date"].notna().any() else date.today()
        date_range = st.date_input("Khoảng thời gian", (date_min, date_max))
    with c3:
        search = st.text_input("Tìm tên LIVE / username")

    # Chỉ phân tích Creator đã khai báo trong Net và có % MCN > 0
    active_users = {u for u, pct in get_creator_map().items() if pct > 0}
    f = df[df["username"].isin(active_users)].copy()
    creators = sorted([x for x in f["username"].dropna().unique() if x])
    if creator_filter:
        f = f[f["username"].isin(creator_filter)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f = f[
            (f["date"].dt.date >= date_range[0]) &
            (f["date"].dt.date <= date_range[1])
        ]
    if search:
        s = search.lower()
        f = f[
            f["username"].str.lower().str.contains(s, na=False)
            | f["live_title"].str.lower().str.contains(s, na=False)
        ]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("GMV Live", fmt_money(f["gmv"].sum()))
    k2.metric("Số buổi LIVE", fmt_number(f["live_id"].nunique()))
    k3.metric("Lượt xem", fmt_number(f["views"].sum()))
    k4.metric("Đơn hàng SKU", fmt_number(f["sku_orders"].sum()))
    k5.metric("Follower mới", fmt_number(f["new_followers"].sum()))

    st.divider()

    by_creator = (
        f.groupby("username", as_index=False)
        .agg(
            GMV=("gmv", "sum"),
            Buổi_LIVE=("live_id", "nunique"),
            Lượt_xem=("views", "sum"),
            Đơn_hàng=("sku_orders", "sum"),
            Follower_mới=("new_followers", "sum"),
            Thời_lượng=("duration_sec", "sum"),
        )
        .sort_values("GMV", ascending=False)
    )
    if not by_creator.empty:
        by_creator["Thời lượng"] = by_creator["Thời_lượng"].apply(seconds_to_hms)
        by_creator = by_creator.drop(columns=["Thời_lượng"])
        st.markdown("### 📊 Hiệu quả theo Creator")
        st.dataframe(
            by_creator.rename(columns={
                "username": "Username",
                "Buổi_LIVE": "Buổi LIVE",
                "Lượt_xem": "Lượt xem",
                "Đơn_hàng": "Đơn hàng SKU",
                "Follower_mới": "Follower mới",
            }),
            use_container_width=True,
            hide_index=True
        )

    st.markdown("### 📄 Chi tiết Live")
    detail = f[[
        "username", "nickname", "live_id", "live_title", "start_time",
        "gmv", "units", "views", "sku_orders", "customers",
        "duration_sec", "new_followers", "products", "impressions",
        "product_clicks", "ctr"
    ]].copy()
    detail["duration_sec"] = detail["duration_sec"].apply(seconds_to_hms)
    detail.columns = [
        "Username", "Biệt danh", "ID LIVE", "Tên LIVE", "Thời gian bắt đầu",
        "GMV", "Số món", "Lượt xem", "Đơn hàng SKU", "Khách hàng",
        "Thời lượng", "Follower mới", "Sản phẩm", "Lượt hiển thị SP",
        "Lượt nhấp SP", "CTR"
    ]
    st.dataframe(detail, use_container_width=True, hide_index=True)

# =========================
# VIDEO ANALYTICS
# =========================
def render_video():
    st.title("🎬 VIDEO ANALYTICS")
    st.caption("Chỉ hiển thị Creator trong Net có % MCN > 0. Hoa hồng MCN được tính theo % của từng Creator.")

    uploaded = st.file_uploader(
        "📤 Upload file Video mới",
        type=["csv"],
        key="video_upload"
    )
    if uploaded:
        if st.button("🚀 Lưu dữ liệu Video", key="save_video"):
            process_video_upload(uploaded.getvalue(), uploaded.name)

    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT v.*, u.file_name, u.period_start, u.period_end
        FROM video_data v
        JOIN uploads u ON v.upload_id = u.id
    """, conn)
    conn.close()

    if df.empty:
        st.info("Chưa có dữ liệu Video. Upload file Video ở phía trên.")
        return

    creators_map = get_creator_map()
    df["share_percent"] = df["username"].map(creators_map).fillna(0)
    df["mcn_commission"] = df["creator_commission"] * df["share_percent"] / 100

    df["date"] = pd.to_datetime(df["post_time"], errors="coerce")

    creators = sorted([x for x in df["username"].dropna().unique() if x])

    c1, c2, c3 = st.columns(3)
    with c1:
        creator_filter = st.multiselect("Creator", creators, key="video_creator_filter")
    with c2:
        date_min = df["date"].min().date() if df["date"].notna().any() else date.today()
        date_max = df["date"].max().date() if df["date"].notna().any() else date.today()
        date_range = st.date_input("Khoảng thời gian", (date_min, date_max), key="video_date")
    with c3:
        search = st.text_input("Tìm video / username", key="video_search")

    # Chỉ phân tích Creator đã khai báo trong Net và có % MCN > 0
    active_users = {u for u, pct in get_creator_map().items() if pct > 0}
    f = df[df["username"].isin(active_users)].copy()
    creators = sorted([x for x in f["username"].dropna().unique() if x])
    if creator_filter:
        f = f[f["username"].isin(creator_filter)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f = f[
            (f["date"].dt.date >= date_range[0]) &
            (f["date"].dt.date <= date_range[1])
        ]
    if search:
        s = search.lower()
        f = f[
            f["username"].str.lower().str.contains(s, na=False)
            | f["title"].str.lower().str.contains(s, na=False)
        ]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("GMV Video", fmt_money(f["gmv"].sum()))
    k2.metric("Hoa hồng NST", fmt_money(f["creator_commission"].sum()))
    k3.metric("Hoa hồng thực tế MCN", fmt_money(f["mcn_commission"].sum()))
    k4.metric("Số Video", fmt_number(f["video_id"].nunique()))
    k5.metric("Lượt xem", fmt_number(f["views"].sum()))

    st.divider()

    by_creator = (
        f.groupby("username", as_index=False)
        .agg(
            GMV=("gmv", "sum"),
            Hoa_hồng_NST=("creator_commission", "sum"),
            Hoa_hồng_MCN=("mcn_commission", "sum"),
            Video=("video_id", "nunique"),
            Lượt_xem=("views", "sum"),
            Like=("likes", "sum"),
            Comment=("comments", "sum"),
            Share=("shares", "sum"),
        )
        .sort_values("Hoa_hồng_MCN", ascending=False)
    )
    if not by_creator.empty:
        st.markdown("### 📊 Hiệu quả theo Creator")
        st.dataframe(
            by_creator.rename(columns={
                "username": "Username",
                "Hoa_hồng_NST": "Hoa hồng ước tính NST",
                "Hoa_hồng_MCN": "Hoa hồng thực tế MCN",
                "Lượt_xem": "Lượt xem",
            }),
            use_container_width=True,
            hide_index=True
        )

    st.markdown("### 📄 Chi tiết Video")
    detail = f[[
        "username", "nickname", "video_id", "title", "post_time",
        "gmv", "creator_commission", "share_percent", "mcn_commission",
        "views", "likes", "comments", "shares", "gpm", "ctr", "ctor"
    ]].copy()
    detail.columns = [
        "Username", "Biệt danh", "ID Video", "Tên Video", "Ngày đăng",
        "GMV", "Hoa hồng NST", "% MCN", "Hoa hồng thực tế MCN",
        "Lượt xem", "Like", "Comment", "Share", "GPM Video", "CTR", "CTOR"
    ]
    st.dataframe(detail, use_container_width=True, hide_index=True)

# =========================
# DASHBOARD / MONTHLY OVERVIEW
# =========================
def get_overview_periods():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT DISTINCT period_start, period_end
        FROM overview_data
        WHERE period_start <> ''
        ORDER BY period_start DESC
    """, conn)
    conn.close()
    return df


def load_latest_overview_for_period(period_start, period_end):
    conn = get_conn()
    uploads = pd.read_sql_query("""
        SELECT id, file_name, uploaded_at
        FROM uploads
        WHERE source = 'Overview'
          AND period_start = ?
          AND period_end = ?
        ORDER BY uploaded_at DESC
    """, conn, params=(period_start, period_end))
    if uploads.empty:
        conn.close()
        return pd.DataFrame(), None
    upload_id = int(uploads.iloc[0]["id"])
    df = pd.read_sql_query(
        "SELECT * FROM overview_data WHERE upload_id = ?",
        conn, params=(upload_id,)
    )
    conn.close()
    return df, uploads.iloc[0].to_dict()


def render_overview_analysis():
    st.caption("Nguồn dữ liệu Tổng quan là file Custom Report Creator theo từng tháng.")

    periods = get_overview_periods()
    if periods.empty:
        st.info("Chưa có file Tổng quan. Vào tab 📥 Cập nhật dữ liệu để upload file.")
        return

    labels = [
        f"{r.period_start[:7]} ({r.period_start} → {r.period_end})"
        for r in periods.itertuples()
    ]
    selected_label = st.selectbox("📅 Chọn tháng", labels, key="overview_month")
    selected_idx = labels.index(selected_label)
    period_start = periods.iloc[selected_idx]["period_start"]
    period_end = periods.iloc[selected_idx]["period_end"]

    df, meta = load_latest_overview_for_period(period_start, period_end)
    if df.empty:
        st.warning("Không có dữ liệu cho kỳ đã chọn.")
        return

    creator_df = get_creators()
    if creator_df.empty:
        st.warning("Chưa có Creator trong DATA CREATOR.")
        return

    creator_df["__creator_key"] = creator_df["username"].apply(normalize_creator_key)
    creator_df["share_percent"] = pd.to_numeric(
        creator_df["share_percent"], errors="coerce"
    ).fillna(0)

    # Chỉ Creator có % MCN > 0 mới tham gia Analytics.
    active = creator_df[creator_df["share_percent"] > 0].copy()
    active_map = {
        row["__creator_key"]: float(row["share_percent"])
        for _, row in active.iterrows()
    }
    display_name_map = {
        row["__creator_key"]: row["username"]
        for _, row in active.iterrows()
    }

    df["__creator_key"] = df["username"].apply(normalize_creator_key)
    df["share_percent"] = df["__creator_key"].map(active_map).fillna(0)
    df = df[df["share_percent"] > 0].copy()
    df["username"] = df["__creator_key"].map(display_name_map).fillna(df["username"])
    df["mcn_commission"] = df["creator_commission"] * df["share_percent"] / 100

    if df.empty:
        st.warning("Tháng này chưa có dữ liệu của Creator có % MCN > 0.")
        return

    total_gmv = df["gmv"].sum()
    total_creator_commission = df["creator_commission"].sum()
    total_mcn = df["mcn_commission"].sum()
    creator_count = df["username"].nunique()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("NST có chia hoa hồng", fmt_number(creator_count))
    k2.metric("GMV", fmt_money(total_gmv))
    k3.metric("Hoa hồng ước tính NST", fmt_money(total_creator_commission))
    k4.metric("Hoa hồng thực tế MCN", fmt_money(total_mcn))
    st.caption("Hoa hồng thực tế MCN = Hoa hồng ước tính NST (cột W) × % MCN trong DATA CREATOR.")
    st.caption(f"Đang xem: {meta['file_name']} · Upload: {meta['uploaded_at']}")

    st.divider()

    # Bảng chính: Creator có phát sinh hoa hồng trong tháng.
    summary = (
        df.groupby("username", as_index=False)
        .agg(
            GMV=("gmv", "sum"),
            Hoa_hồng_NST=("creator_commission", "sum"),
            **{"% MCN": ("share_percent", "first")},
            **{"Hoa_hồng_MCN": ("mcn_commission", "sum")},
            **{"GMV_Live": ("live_gmv", "sum")},
            **{"GMV_Video": ("video_gmv", "sum")},
        )
        .sort_values("Hoa_hồng_MCN", ascending=False)
    )
    summary = summary.rename(columns={
        "username": "NST",
        "Hoa_hồng_NST": "Hoa hồng ước tính NST",
        "Hoa_hồng_MCN": "Hoa hồng thực tế MCN",
        "GMV_Live": "GMV Live",
        "GMV_Video": "GMV Video",
    })

    # Top Creator: chỉ giữ bảng xếp hạng, không hiển thị thêm bảng "Hoa hồng theo Creator".
    st.markdown("### 🏆 Top Creator theo GMV")
    top_creator = (
        summary[["NST", "GMV", "Hoa hồng ước tính NST", "% MCN", "Hoa hồng thực tế MCN"]]
        .sort_values("GMV", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )
    st.dataframe(top_creator, use_container_width=True, hide_index=True)

    # Top Product: dữ liệu lấy từ file Product riêng, không lấy từ Overview/Live/Video.
    st.markdown("### 📦 Top sản phẩm theo GMV")
    st.info("Chưa có dữ liệu Product. Vào 📥 Cập nhật dữ liệu để upload file Product.")

    st.markdown("### 📄 Dữ liệu Tổng quan chi tiết")
    detail_cols = [
        "username", "followers", "gmv", "orders",
        "live_gmv", "video_gmv", "live_orders", "video_orders",
        "live_ctr", "video_ctr", "creator_commission", "commission_base",
        "live_views", "views", "live_sessions", "videos",
        "share_percent", "mcn_commission"
    ]
    detail = df[detail_cols].copy()
    detail.columns = [
        "Username", "Follower", "GMV", "Đơn hàng",
        "GMV Live", "GMV Video", "Đơn Live", "Đơn Video",
        "CTR Live", "CTR Video", "Hoa hồng ước tính NST (cột W)", "Cơ sở tính HH",
        "Lượt xem LIVE", "Lượt xem", "Buổi LIVE", "Video",
        "% MCN", "Hoa hồng thực tế MCN"
    ]
    st.dataframe(detail, use_container_width=True, hide_index=True)


def render_overview_update():
    st.markdown("### 📥 Cập nhật dữ liệu")
    st.caption("Upload dữ liệu nguồn tại đây. Trang 📈 Phân tích chỉ dùng để xem dashboard.")

    st.markdown("#### 📊 1. Overview Creator")
    st.caption("File TikTok Custom Report Creator · sheet 'Báo cáo tùy chỉnh'.")
    uploaded = st.file_uploader(
        "Upload file Tổng quan Creator",
        type=["xlsx", "xls"],
        key="overview_upload",
        help="Ví dụ: CustomReport_Creator 2026-09-01_2026-09-30.xlsx"
    )
    if uploaded:
        if st.button("🚀 Lưu dữ liệu Tổng quan", key="save_overview"):
            process_overview_upload(uploaded.getvalue(), uploaded.name)

    st.divider()

    st.markdown("#### 📦 2. Product")
    st.caption("File Product sẽ dùng riêng để xếp hạng sản phẩm theo GMV. Chưa xử lý dữ liệu cho đến khi xác định đúng cấu trúc cột của file Product.")
    product_upload = st.file_uploader(
        "Upload file Product (chuẩn bị)",
        type=["xlsx", "xls", "csv"],
        key="product_upload",
    )
    if product_upload:
        st.info("Đã nhận file Product. Khi có file mẫu thực tế, mình sẽ map đúng cột và thêm lưu trữ + Top Product theo GMV.")
        st.dataframe(pd.DataFrame({"Tên file": [product_upload.name], "Kích thước": [f"{len(product_upload.getvalue())/1024:.1f} KB"]}), hide_index=True, use_container_width=True)


def render_dashboard():
    st.title("📊 TỔNG QUAN")
    tab_analysis, tab_update = st.tabs(["📈 Phân tích", "📥 Cập nhật dữ liệu"])

    with tab_analysis:
        render_overview_analysis()

    with tab_update:
        render_overview_update()

# =========================
# HISTORY
# =========================
def render_history():
    st.title("📚 LỊCH SỬ DỮ LIỆU")
    st.caption("Danh sách các file Live/Video đã upload vào hệ thống.")

    df = load_uploads()
    if df.empty:
        st.info("Chưa có file nào được upload.")
        return

    show = df[[
        "id", "source", "file_name", "uploaded_at",
        "row_count", "period_start", "period_end"
    ]].copy()
    show.columns = [
        "ID", "Loại", "Tên file", "Thời gian upload",
        "Số dòng", "Từ ngày", "Đến ngày"
    ]
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("### 🗑️ Xóa một lần upload")
    options = df["id"].tolist()
    selected_id = st.selectbox(
        "Chọn ID upload cần xóa",
        options,
        format_func=lambda x: f"ID {x} — {df.loc[df['id'] == x, 'source'].iloc[0]} — {df.loc[df['id'] == x, 'file_name'].iloc[0]}"
    )
    if st.button("🗑️ Xóa dữ liệu upload này", type="secondary"):
        delete_upload(int(selected_id))
        st.success("Đã xóa upload và toàn bộ dữ liệu thuộc file đó.")
        st.rerun()


# =========================
# SETTINGS / THEME
# =========================
def render_settings():
    st.title("⚙️ CÀI ĐẶT")
    st.caption("Tối giản, sáng/tối theo lựa chọn hoặc theo giao diện máy.")

    st.markdown("### 🎨 Giao diện")
    theme_options = ["☀️ Sáng", "🌙 Tối", "🌓 Theo hệ thống"]
    current = st.session_state.get("theme_mode", "🌓 Theo hệ thống")
    theme = st.radio(
        "Chế độ hiển thị",
        theme_options,
        index=theme_options.index(current) if current in theme_options else 2,
        horizontal=True,
        key="theme_picker",
    )
    if theme != current:
        st.session_state["theme_mode"] = theme
        set_setting("theme_mode", theme)
        st.rerun()

    st.markdown("### 🖼️ Hình nền")
    bg = st.file_uploader(
        "Upload hình nền",
        type=["png", "jpg", "jpeg", "webp"],
        key="mcn_background",
        help="Hình nền được lưu vào cấu hình app và hiển thị nhẹ phía sau nội dung."
    )

    if bg is not None:
        encoded = base64.b64encode(bg.getvalue()).decode()
        mime = bg.type or "image/png"
        css_value = f"url(data:{mime};base64,{encoded})"
        st.session_state["mcn_bg_css"] = css_value
        set_setting("mcn_bg_css", css_value)
        st.success("Đã lưu và áp dụng hình nền.")

    if st.button("🗑️ Xóa hình nền", use_container_width=False):
        st.session_state["mcn_bg_css"] = ""
        set_setting("mcn_bg_css", "")
        st.rerun()

    st.markdown("### 👀 Xem trước")
    bg_css = st.session_state.get("mcn_bg_css", "")
    preview_style = (
        "height:180px;border-radius:14px;"
        "border:1px solid rgba(128,128,128,.25);"
        "background-size:cover;background-position:center;"
    )
    if bg_css:
        preview_style += f"background-image:{bg_css};"
    else:
        preview_style += "background:linear-gradient(135deg,#f7f7f7,#ffffff);"
    st.markdown(f'<div style="{preview_style}"></div>', unsafe_allow_html=True)


def apply_theme_css():
    mode = st.session_state.get("theme_mode", "🌓 Theo hệ thống")
    bg_css = st.session_state.get("mcn_bg_css", "")

    if mode == "☀️ Sáng":
        theme_css = """
        :root { color-scheme: light; }
        .stApp { background: #ffffff; color: #111111; }
        [data-testid="stSidebar"] { background: #f7f7f7; }
        """
    elif mode == "🌙 Tối":
        theme_css = """
        :root { color-scheme: dark; }
        .stApp { background: #0f0f0f; color: #f5f5f5; }
        [data-testid="stSidebar"] { background: #151515; }
        """
    else:
        theme_css = """
        :root { color-scheme: light dark; }
        @media (prefers-color-scheme: dark) {
            .stApp { background: #0f0f0f; color: #f5f5f5; }
            [data-testid="stSidebar"] { background: #151515; }
        }
        @media (prefers-color-scheme: light) {
            .stApp { background: #ffffff; color: #111111; }
            [data-testid="stSidebar"] { background: #f7f7f7; }
        }
        """

    background_css = ""
    if bg_css:
        background_css = f"""
        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            background-image: {bg_css};
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            opacity: .07;
            pointer-events: none;
            z-index: 0;
        }}
        .stApp > div {{ position: relative; z-index: 1; }}
        """

    st.markdown(f"<style>{theme_css}{background_css}</style>", unsafe_allow_html=True)

apply_theme_css()

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## SINGO MCN")
    st.caption("Creator Network Analytics")
    st.divider()

    page = st.radio(
        "MENU",
        [
            "📊 Tổng quan",
            "👥 DATA CREATOR",
            "🔴 LIVE ANALYTICS",
            "🎬 VIDEO ANALYTICS",
            "📚 Lịch sử dữ liệu",
            "⚙️ Cài đặt",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    creators_count = len(get_creators())
    st.caption(f"👥 {creators_count} Creator trong Net")

if page == "📊 Tổng quan":
    render_dashboard()
elif page == "👥 DATA CREATOR":
    render_creators()
elif page == "🔴 LIVE ANALYTICS":
    render_live()
elif page == "🎬 VIDEO ANALYTICS":
    render_video()
elif page == "📚 Lịch sử dữ liệu":
    render_history()
elif page == "⚙️ Cài đặt":
    render_settings()
