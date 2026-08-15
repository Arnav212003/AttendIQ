import qrcode
from io import BytesIO


def create_subject_qr(subject_code):
    subject_code = str(subject_code).strip().upper()
    qr_text = f"ATTENDIQ_SUBJECT_CODE:{subject_code}"

    qr = qrcode.make(qr_text)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def get_share_message(subject_name, subject_code, section):
    subject_name = str(subject_name).strip()
    subject_code = str(subject_code).strip().upper()
    section = str(section).strip()

    return (
        f"Join my AttendIQ subject\n\n"
        f"Subject: {subject_name}\n"
        f"Section: {section}\n"
        f"Join Code: {subject_code}\n\n"
        f"Open Student Portal → Join Subject → Enter this code."
    )
