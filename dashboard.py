# 📦 Import library
from google.colab import files
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import storage
import pandas as pd
import time
import re

# 📎 Upload file: JSON + sector.csv
print("📎 Silakan upload file JSON key service account & sector.csv...")
uploaded = files.upload()
json_file_name = [f for f in uploaded if f.endswith('.json')][0]
sector_file_name = [f for f in uploaded if f.lower().startswith('sector') and f.endswith('.csv')][0]

# ⚙️ Konfigurasi
SERVICE_ACCOUNT_FILE = json_file_name
FOLDER_ID = '1_BL0w0TyFG-Mo-zr8OiKMzqqct92pTKo'
SHEET_NAME = 'Sheet1'
GCS_BUCKET = 'stock-csvku'
GCS_FILENAME = 'hasil_gabungan.csv'

# 🔐 Setup credentials
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=[
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/devstorage.full_control'
    ]
)

# 🗓️ Fungsi konversi tanggal Indonesia → datetime
def convert_indonesian_date(date_str):
    bulan_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "Mei": "05", "Jun": "06",
        "Jul": "07", "Agt": "08", "Sep": "09", "Okt": "10", "Nov": "11", "Des": "12"
    }
    try:
        for indo, num in bulan_map.items():
            if indo in date_str:
                return pd.to_datetime(date_str.replace(indo, num), format="%d %m %Y")
        return pd.to_datetime(date_str, errors='coerce')
    except:
        return pd.NaT

def extract_date_from_filename(filename):
    match = re.search(r"(\d{8})", filename)
    if match:
        try:
            return pd.to_datetime(match.group(1), format="%Y%m%d")
        except:
            return pd.NaT
    return pd.NaT

def get_sheets_in_folder(folder_id):
    drive_service = build('drive', 'v3', credentials=credentials)
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
    all_files = []
    page_token = None
    while True:
        try:
            results = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token
            ).execute()
            files_list = results.get('files', [])
            if not files_list:
                break
            all_files.extend(files_list)
            print(f"✅ Ditemukan {len(files_list)} file. Total: {len(all_files)}")
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        except Exception as e:
            print(f"❌ Error Drive API: {e}")
            break
    return all_files

def read_sheet_data(sheet_id, sheet_name, max_retries=3):
    sheets_service = build('sheets', 'v4', credentials=credentials)
    range_name = f"{sheet_name}!A:Z"
    for attempt in range(max_retries):
        try:
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=sheet_id, range=range_name).execute()
            return result.get('values', [])
        except Exception as e:
            print(f"⚠️ Gagal baca sheet (percobaan {attempt+1}): {e}")
            time.sleep(5)
    return []

def upload_to_gcs(dataframe, bucket_name, destination_blob_name, max_retries=3):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    csv_data = dataframe.to_csv(index=False)
    for attempt in range(max_retries):
        try:
            print(f"📤 Upload ke GCS: {destination_blob_name} (percobaan {attempt+1})")
            blob.upload_from_string(csv_data, content_type='text/csv')
            print(f"✅ Upload sukses ke {bucket_name}/{destination_blob_name}")
            return True
        except Exception as e:
            print(f"⚠️ Upload gagal: {e}")
            time.sleep(10)
    return False

def main():
    print("🚀 Mulai proses penggabungan...")
    all_data = []
    sheets = get_sheets_in_folder(FOLDER_ID)
    if not sheets:
        print("⚠️ Tidak ada file ditemukan.")
        return

    headers = None
    for i, sheet in enumerate(sheets):
        print(f"📄 Membaca: {sheet['name']} ({i+1}/{len(sheets)})")
        rows = read_sheet_data(sheet['id'], SHEET_NAME)
        if not rows or len(rows) < 2:
            print(f"🚫 Kosong: {sheet['name']}")
            continue
        if i == 0:
            headers = rows[0]
            headers.append("Source File")
        for row in rows[1:]:
            row += [sheet["name"]]
            all_data.append(row)

    if not headers:
        print("❌ Tidak ada data valid.")
        return

    df = pd.DataFrame(all_data, columns=headers)
    print(f"📊 Total baris: {len(df)}")

    # 🔢 Konversi kolom numerik
    for col in ['High', 'Low', 'Close', 'Volume', 'Foreign Buy', 'Foreign Sell', 'Bid Volume', 'Offer Volume', 'Previous']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df["VWAP"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["Last Trading Date"] = df["Last Trading Date"].apply(lambda x: convert_indonesian_date(str(x)))
    df.loc[df["Last Trading Date"].isna(), "Last Trading Date"] = df.loc[df["Last Trading Date"].isna(), "Source File"].apply(extract_date_from_filename)

    df["Week"] = df["Last Trading Date"].dt.isocalendar().week.astype(str).str.zfill(2)
    df["Year"] = df["Last Trading Date"].dt.year.astype(str)
    df["Week"] = df["Week"] + "-" + df["Year"]
    df.drop(columns=["Year"], inplace=True)

    median_volume = df["Volume"].median()
    df["Signal"] = df.apply(lambda row: (
        "Akumulasi" if row["Close"] > row["VWAP"] and row["Volume"] > median_volume
        else "Distribusi" if row["Close"] < row["VWAP"] and row["Volume"] > median_volume
        else "Netral"
    ), axis=1)

    df["Money Flow"] = df["VWAP"] * df["Volume"]
    df.sort_values(by=["Stock Code", "Last Trading Date"], inplace=True)
    df["Prev VWAP"] = df.groupby("Stock Code")["VWAP"].shift(1)
    df["Flow Direction"] = df.apply(
        lambda row: "Positive" if row["VWAP"] > row["Prev VWAP"]
        else "Negative" if row["VWAP"] < row["Prev VWAP"]
        else "Neutral", axis=1
    )
    df["Positive Flow"] = df.apply(lambda row: row["Money Flow"] if row["Flow Direction"] == "Positive" else 0, axis=1)
    df["Negative Flow"] = df.apply(lambda row: row["Money Flow"] if row["Flow Direction"] == "Negative" else 0, axis=1)

    df["PosFlow14"] = df.groupby("Stock Code")["Positive Flow"].transform(lambda x: x.rolling(window=14, min_periods=1).sum())
    df["NegFlow14"] = df.groupby("Stock Code")["Negative Flow"].transform(lambda x: x.rolling(window=14, min_periods=1).sum())

    def calculate_mfi(row):
        pos = row["PosFlow14"]
        neg = row["NegFlow14"]
        if neg == 0:
            return 100
        ratio = pos / neg
        return round(100 - (100 / (1 + ratio)), 2)

    df["MFI14"] = df.apply(calculate_mfi, axis=1)
    df["MFI Signal"] = df["MFI14"].apply(lambda mfi: "Overbought" if mfi >= 80 else "Oversold" if mfi <= 20 else "Normal")

    df["Foreign Flow"] = df.apply(lambda row: "Inflow" if row["Foreign Buy"] > row["Foreign Sell"] * 2
                                   else "Outflow" if row["Foreign Sell"] > row["Foreign Buy"] * 2
                                   else "Netral", axis=1)

    df["Bid/Offer Imbalance"] = df.apply(lambda row: 0 if pd.isna(row["Bid Volume"]) or pd.isna(row["Offer Volume"]) or (row["Bid Volume"] + row["Offer Volume"]) == 0
                                          else (row["Bid Volume"] - row["Offer Volume"]) / (row["Bid Volume"] + row["Offer Volume"]), axis=1)

    df["Final Signal"] = df.apply(lambda row: "Strong Akumulasi" if row["Signal"] == "Akumulasi" and row["Bid/Offer Imbalance"] > 0.3
                                   else "Strong Distribusi" if row["Signal"] == "Distribusi" and row["Bid/Offer Imbalance"] < -0.3
                                   else row["Signal"], axis=1)

    df["Unusual Volume"] = df["Volume"] > (2 * median_volume)

    sector_df = pd.read_csv(sector_file_name)
    df = df.merge(sector_df, how='left', left_on='Stock Code', right_on='Stock Code')
    df['Sector'] = df['Sector'].fillna('Others')

    print("📤 Upload ke Google Cloud Storage...")
    success = upload_to_gcs(df, GCS_BUCKET, GCS_FILENAME)

    if success:
        print("🎉 Berhasil! File tersimpan di GCS.")
    else:
        print("⚠️ Gagal upload ke GCS.")

if __name__ == "__main__":
    main()
