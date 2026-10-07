
import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
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
    s = s.replace("₫", "").replace("đ", "").replace("Đ", "")
    s = s.replace(" ", "")
    # TikTok exports Vietnamese currency as 175.921.083
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    else:
        s = s.replace(",", "")
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
        str(r["username"]).strip().lower(): float(r["share_percent"] or 0)
        for _, r in df.iterrows()
    }

def normalize_username(x):
    return clean_text(x).lstrip("@").lower()

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
        share = creator_map.get(username, 0)
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

# =========================
# LIVE ANALYTICS
# =========================
def render_live():
    st.title("🔴 LIVE ANALYTICS")
    st.caption("Upload file Live mới tại đây. Dữ liệu được lưu cộng dồn theo từng file.")

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

    f = df.copy()
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
    st.caption("Upload file Video mới tại đây. Hoa hồng MCN được tính theo % của từng Creator.")

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

    f = df.copy()
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
                "Hoa_hồng_NST": "Hoa hồng NST",
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
# DASHBOARD
# =========================
def render_dashboard():
    st.title("📊 TỔNG QUAN")
    st.caption("Tổng hợp dữ liệu MCN từ Live và Video đã upload.")

    conn = get_conn()
    creators = pd.read_sql_query("SELECT * FROM creators", conn)
    video = pd.read_sql_query("SELECT * FROM video_data", conn)
    live = pd.read_sql_query("SELECT * FROM live_data", conn)
    conn.close()

    total_creators = len(creators)
    video_gmv = video["gmv"].sum() if not video.empty else 0
    video_commission = video["creator_commission"].sum() if not video.empty else 0
    creator_map = get_creator_map()
    video_mcn = 0
    if not video.empty:
        video_mcn = sum(
            row["creator_commission"] * creator_map.get(str(row["username"]).lower(), 0) / 100
            for _, row in video.iterrows()
        )

    live_gmv = live["gmv"].sum() if not live.empty else 0
    live_sessions = live["live_id"].nunique() if not live.empty else 0
    video_count = video["video_id"].nunique() if not video.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Creator trong Net", fmt_number(total_creators))
    c2.metric("GMV Live", fmt_money(live_gmv))
    c3.metric("GMV Video", fmt_money(video_gmv))
    c4.metric("Hoa hồng MCN", fmt_money(video_mcn))

    c5, c6, c7 = st.columns(3)
    c5.metric("Hoa hồng NST từ Video", fmt_money(video_commission))
    c6.metric("Số buổi LIVE", fmt_number(live_sessions))
    c7.metric("Số Video", fmt_number(video_count))

    st.divider()

    if not video.empty:
        v = video.copy()
        v["mcn_commission"] = v.apply(
            lambda r: r["creator_commission"] * creator_map.get(str(r["username"]).lower(), 0) / 100,
            axis=1
        )
        top = (
            v.groupby("username", as_index=False)
            .agg(
                GMV=("gmv", "sum"),
                **{"Hoa hồng MCN": ("mcn_commission", "sum")}
            )
            .sort_values("Hoa hồng MCN", ascending=False)
            .head(10)
        )
        if not top.empty:
            st.markdown("### 🏆 Top Creator theo hoa hồng MCN từ Video")
            chart = top.set_index("username")[["Hoa hồng MCN"]]
            st.bar_chart(chart)

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
