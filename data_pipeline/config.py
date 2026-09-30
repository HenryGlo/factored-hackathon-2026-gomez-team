"""Metadatos del dataset que usa el pipeline CSV → DuckDB → PostgreSQL.

Movido desde dashboard/src/config.py (material local no versionado) para que la
construcción de la base DuckDB sea reproducible desde el repo. DICTIONARY transcribe
el diccionario oficial (LATAM_Bank_Complete_Data_Dictionary) solo para tipar;
build_duckdb.py descubre el esquema real de los archivos y nunca asume que estas
columnas existen.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / ".env")


def _path(var: str, default: str) -> Path:
    p = Path(os.environ.get(var) or default)
    return p if p.is_absolute() else REPO / p


RAW_DATA_DIR = _path("RAW_DATA_DIR", "dataset/data")
DUCKDB_PATH = _path("DUCKDB_PATH", "data/bank.duckdb")
WORK_DIR = REPO / "data" / "processed" / "etl"   # CSV intermedios del COPY; fuera de git
SEED = 42

# Tokens que en los CSV significan "sin dato" (p. ej. origin_interaction_id llega como "NaN").
NULL_TOKENS = ("", "nan", "none", "null", "na", "n/a")

# Columnas de país a normalizar ("Mexico" y "México" conviven en el origen).
COUNTRY_FIX = {"Mexico": "México", "mexico": "México", "MEXICO": "México"}


def _cols(spec):
    return dict(tok.split(":") for tok in spec.split())


DICTIONARY = {
    "customers": _cols("""customer_id:VARCHAR document_number:VARCHAR document_type:VARCHAR first_name:VARCHAR
        last_name:VARCHAR date_of_birth:DATE gender:VARCHAR email:VARCHAR mobile_phone:VARCHAR landline_phone:VARCHAR
        address:VARCHAR city:VARCHAR state:VARCHAR country:VARCHAR postal_code:VARCHAR detected_accent:VARCHAR
        segment:VARCHAR credit_score:INTEGER estimated_monthly_income:DOUBLE occupation:VARCHAR marital_status:VARCHAR
        education_level:VARCHAR registration_date:TIMESTAMP registration_branch_id:VARCHAR customer_status:VARCHAR
        last_updated:TIMESTAMP accepts_marketing:BOOLEAN"""),
    "products": _cols("""product_id:VARCHAR customer_id:VARCHAR product_type:VARCHAR product_number:VARCHAR
        currency:VARCHAR current_balance:DOUBLE credit_limit:DOUBLE interest_rate:DOUBLE opening_date:DATE
        expiration_date:DATE opening_branch_id:VARCHAR product_status:VARCHAR opening_channel:VARCHAR
        has_linked_app:BOOLEAN days_past_due:INTEGER last_transaction_date:TIMESTAMP last_updated:TIMESTAMP"""),
    "branches": _cols("""branch_id:VARCHAR branch_code:VARCHAR branch_name:VARCHAR branch_type:VARCHAR address:VARCHAR
        city:VARCHAR state:VARCHAR country:VARCHAR postal_code:VARCHAR geographic_zone:VARCHAR phone:VARCHAR
        email:VARCHAR opening_time:TIME closing_time:TIME has_atms:BOOLEAN atm_count:INTEGER
        has_teller_windows:BOOLEAN teller_window_count:INTEGER latitude:DOUBLE longitude:DOUBLE
        branch_opening_date:DATE branch_status:VARCHAR"""),
    "service_agents": _cols("""agent_id:VARCHAR employee_code:VARCHAR first_name:VARCHAR last_name:VARCHAR
        email:VARCHAR phone:VARCHAR native_accent:VARCHAR country_of_origin:VARCHAR assigned_branch_id:VARCHAR
        agent_type:VARCHAR experience_level:VARCHAR languages:VARCHAR specialty:VARCHAR hire_date:DATE
        avg_csat:DOUBLE total_monthly_interactions:INTEGER agent_status:VARCHAR work_shift:VARCHAR"""),
    "marketing_campaigns": _cols("""campaign_id:VARCHAR campaign_name:VARCHAR description:VARCHAR
        campaign_type:VARCHAR campaign_objective:VARCHAR promoted_product:VARCHAR target_segment:VARCHAR
        target_country:VARCHAR start_date:DATE end_date:DATE budget:DOUBLE campaign_status:VARCHAR
        expected_conversion_rate:DOUBLE"""),
    "transactions": _cols("""transaction_id:VARCHAR transaction_date:TIMESTAMP process_date:DATE product_id:VARCHAR
        customer_id:VARCHAR transaction_type:VARCHAR transaction_category:VARCHAR amount:DOUBLE currency:VARCHAR
        amount_usd:DOUBLE channel:VARCHAR branch_id:VARCHAR merchant_name:VARCHAR merchant_category:VARCHAR
        transaction_country:VARCHAR transaction_city:VARCHAR transaction_status:VARCHAR response_code:VARCHAR
        is_fraud:BOOLEAN fraud_score:DOUBLE latitude:DOUBLE longitude:DOUBLE"""),
    "call_center_interactions": _cols("""interaction_id:VARCHAR interaction_date:TIMESTAMP process_date:DATE
        customer_id:VARCHAR agent_id:VARCHAR interaction_type:VARCHAR channel:VARCHAR contact_reason:VARCHAR
        reason_category:VARCHAR duration_seconds:INTEGER wait_time_seconds:INTEGER was_resolved:BOOLEAN
        requires_followup:BOOLEAN detected_sentiment:VARCHAR sentiment_score:DOUBLE customer_detected_accent:VARCHAR
        agent_used_accent:VARCHAR was_escalated:BOOLEAN mentioned_products:VARCHAR has_transcript:BOOLEAN
        has_recording:BOOLEAN"""),
    "call_transcripts": _cols("""transcript_id:VARCHAR interaction_id:VARCHAR process_date:DATE customer_id:VARCHAR
        agent_id:VARCHAR full_text:VARCHAR customer_text:VARCHAR agent_text:VARCHAR detected_language:VARCHAR
        detected_accent:VARCHAR accent_confidence:DOUBLE detected_keywords:VARCHAR mentioned_entities:VARCHAR
        detected_intents:VARCHAR main_topics:VARCHAR transcription_model:VARCHAR audio_quality:VARCHAR
        duration_seconds:INTEGER"""),
    "satisfaction_surveys": _cols("""survey_id:VARCHAR survey_date:TIMESTAMP process_date:DATE interaction_id:VARCHAR
        customer_id:VARCHAR agent_id:VARCHAR survey_type:VARCHAR send_channel:VARCHAR main_score:INTEGER
        nps_category:VARCHAR question_1_text:VARCHAR question_1_response:INTEGER question_2_text:VARCHAR
        question_2_response:INTEGER question_3_text:VARCHAR question_3_response:INTEGER open_comments:VARCHAR
        comment_sentiment:VARCHAR response_time_hours:DOUBLE campaign_response_rate:DOUBLE"""),
    "digital_events": _cols("""event_id:VARCHAR event_date:TIMESTAMP process_date:DATE customer_id:VARCHAR
        session_id:VARCHAR event_type:VARCHAR event_category:VARCHAR channel:VARCHAR platform:VARCHAR
        browser:VARCHAR app_version:VARCHAR page_url:VARCHAR page_title:VARCHAR action:VARCHAR element_id:VARCHAR
        product_id:VARCHAR event_value:DOUBLE duration_seconds:INTEGER ip_address:VARCHAR ip_country:VARCHAR
        ip_city:VARCHAR is_mobile:BOOLEAN referrer:VARCHAR utm_source:VARCHAR utm_medium:VARCHAR
        utm_campaign:VARCHAR"""),
    "complaints": _cols("""complaint_id:VARCHAR creation_date:TIMESTAMP process_date:DATE customer_id:VARCHAR
        case_type:VARCHAR category:VARCHAR subcategory:VARCHAR reception_channel:VARCHAR
        affected_product_id:VARCHAR related_branch_id:VARCHAR origin_interaction_id:VARCHAR description:VARCHAR
        claimed_amount:DOUBLE currency:VARCHAR priority:VARCHAR status:VARCHAR assigned_agent_id:VARCHAR
        assignment_date:TIMESTAMP first_response_date:TIMESTAMP resolution_date:TIMESTAMP closing_date:TIMESTAMP
        sla_breached:BOOLEAN resolution_days:INTEGER resolution:VARCHAR compensation_granted:DOUBLE
        resolution_satisfaction:INTEGER is_repeat_complainer:BOOLEAN"""),
    "campaign_sends": _cols("""send_id:VARCHAR send_date:TIMESTAMP process_date:DATE campaign_id:VARCHAR
        customer_id:VARCHAR send_channel:VARCHAR template_used:VARCHAR subject:VARCHAR send_status:VARCHAR
        was_delivered:BOOLEAN was_opened:BOOLEAN open_date:TIMESTAMP was_clicked:BOOLEAN click_date:TIMESTAMP
        click_count:INTEGER had_conversion:BOOLEAN conversion_date:TIMESTAMP conversion_value:DOUBLE
        open_device:VARCHAR open_country:VARCHAR failure_reason:VARCHAR send_cost:DOUBLE"""),
    "daily_exchange_rates": _cols("""date:DATE source_currency:VARCHAR target_currency:VARCHAR
        exchange_rate:DOUBLE buy_rate:DOUBLE sell_rate:DOUBLE source:VARCHAR"""),
}

# pk, fecha del evento, canal, filas esperadas segun el diccionario, clave de duplicado por contenido.
TABLES = {
    "customers": dict(pk=["customer_id"], date=None, channel=None, expected=150_000,
                      content_key=["document_number"], order="last_updated"),
    "products": dict(pk=["product_id"], date=None, channel="opening_channel", expected=400_000,
                     content_key=["product_number"], order="last_updated"),
    "branches": dict(pk=["branch_id"], date=None, channel=None, expected=350, content_key=["branch_code"]),
    "service_agents": dict(pk=["agent_id"], date=None, channel=None, expected=1_200,
                           content_key=["employee_code"]),
    "marketing_campaigns": dict(pk=["campaign_id"], date=None, channel="campaign_type", expected=200,
                                content_key=["campaign_name"]),
    "daily_exchange_rates": dict(pk=["date", "source_currency", "target_currency"], date="date", channel=None,
                                 expected=3_000, content_key=["date", "source_currency", "target_currency"]),
    "transactions": dict(pk=["transaction_id"], date="transaction_date", channel="channel", expected=5_000_000,
                         content_key=["customer_id", "amount", "transaction_date"]),
    "call_center_interactions": dict(pk=["interaction_id"], date="interaction_date", channel="channel",
                                     expected=800_000, content_key=["customer_id", "interaction_date", "agent_id"]),
    "call_transcripts": dict(pk=["transcript_id"], date="process_date", channel=None, expected=200_000,
                             content_key=["interaction_id"]),
    "satisfaction_surveys": dict(pk=["survey_id"], date="survey_date", channel="send_channel", expected=250_000,
                                 content_key=["interaction_id", "survey_type"]),
    "digital_events": dict(pk=["event_id"], date="event_date", channel="channel", expected=10_000_000,
                           content_key=["session_id", "event_date", "event_type"]),
    "complaints": dict(pk=["complaint_id"], date="creation_date", channel="reception_channel", expected=80_000,
                       content_key=["customer_id", "creation_date", "category"]),
    "campaign_sends": dict(pk=["send_id"], date="send_date", channel="send_channel", expected=2_000_000,
                           content_key=["campaign_id", "customer_id"]),
}
FACT_TABLES = ["transactions", "call_center_interactions", "call_transcripts", "satisfaction_surveys",
               "digital_events", "complaints", "campaign_sends"]
