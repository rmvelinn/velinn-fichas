from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os, secrets, requests as req, json, base64, io
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
import google.auth.transport.requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.enums import TA_CENTER

EMAIL_FROM   = os.environ.get("EMAIL_FROM",   "no-reply@velinn.com")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "marcelo.brandao@velinn.com")
GMAIL_SA_JSON = os.environ.get("GMAIL_SA_JSON", "")
DRIVE_SA_JSON = os.environ.get("DRIVE_SA_JSON", GMAIL_SA_JSON)
HUB_URL       = os.environ.get("HUB_URL",  "https://velinn-hub.onrender.com")
NOTIF_EMAILS        = [e.strip() for e in os.environ.get("NOTIF_EMAILS", "").split(",") if e.strip()]
FICHAS_NOTIF_SECRET = os.environ.get("FICHAS_NOTIF_SECRET", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def db_select(table, params=None):
    r = req.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params or {})
    return r.json() if r.ok else []


def db_update(table, data, params):
    r = req.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), json=data, params=params)
    return r.ok


def _gmail_token():
    sa_info = json.loads(GMAIL_SA_JSON)
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    ).with_subject(EMAIL_SENDER)
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _enviar_email(para: str, assunto: str, corpo: str, html: str = ""):
    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = assunto
            msg["From"] = EMAIL_FROM
            msg["To"] = para
            msg.attach(MIMEText(corpo, "plain"))
            msg.attach(MIMEText(html, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        else:
            m = EmailMessage()
            m["Subject"] = assunto
            m["From"] = EMAIL_FROM
            m["To"] = para
            m.set_content(corpo)
            raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        token = _gmail_token()
        r = req.post(
            f"https://gmail.googleapis.com/gmail/v1/users/{EMAIL_SENDER}/messages/send",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"raw": raw},
        )
        if r.ok:
            print(f"[email] enviado para {para}")
        else:
            print(f"[email] FALHA: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[email] FALHA: {e}")


def _drive_service_rw():
    if not DRIVE_SA_JSON:
        return None
    sa_info = json.loads(DRIVE_SA_JSON)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _drive_get_or_create_folder(svc, parent_id: str, name: str) -> str:
    """Retorna o id de uma subpasta, criando-a se não existir."""
    q = (f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' "
         f"and name='{name}' and trashed=false")
    res = svc.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                           includeItemsFromAllDrives=True).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    f = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return f["id"]


def _buscar_cnpj(cnpj: str) -> dict:
    cnpj_digits = "".join(c for c in (cnpj or "") if c.isdigit())
    if len(cnpj_digits) != 14:
        return {}
    try:
        r = req.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}", timeout=10)
        return r.json() if r.ok else {}
    except Exception as e:
        print(f"[cnpj] FALHA: {e}")
        return {}


def _gerar_pdf_cartao_cnpj(dados: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    gold  = colors.HexColor("#b48c50")
    dark  = colors.HexColor("#1a1a2e")
    white = colors.white
    story = []

    h_title = ParagraphStyle("ht", fontName="Helvetica-Bold", fontSize=14, textColor=gold, leading=18)
    h_sub   = ParagraphStyle("hs", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#cccccc"), leading=14)
    section_style = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=11, textColor=gold, spaceBefore=14, spaceAfter=6)
    label_style = ParagraphStyle("lbl", fontName="Helvetica-Bold", fontSize=9, textColor=dark)
    value_style = ParagraphStyle("val", fontName="Helvetica",      fontSize=9, textColor=dark)

    logo_path = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    logo_cell = RLImage(logo_path, width=2.2*cm, height=0.75*cm) if os.path.exists(logo_path) else Paragraph("VELINN", h_title)
    hdr = Table([[logo_cell, [Paragraph("CARTÃO CNPJ", h_title), Paragraph(dados.get("razao_social",""), h_sub)]]],
                colWidths=[3*cm, 14*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#0d1117")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 12), ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",(0,0),(0,0),14), ("LEFTPADDING",(1,0),(1,0),12),
        ("LINEBELOW",  (0,0),(-1,-1), 3, gold),
    ]))
    story += [hdr, Spacer(1, 12)]

    def row(label, value):
        if not value:
            return []
        return [Table([[Paragraph(label, label_style), Paragraph(str(value), value_style)]],
                      colWidths=[5*cm, 12*cm],
                      style=TableStyle([
                          ("BACKGROUND",(0,0),(-1,-1), colors.HexColor("#f9f5ee")),
                          ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#f9f5ee"), white]),
                          ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
                          ("LEFTPADDING",(0,0),(-1,-1),8), ("LINEBELOW",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),
                      ])), Spacer(1,2)]

    cnpj_fmt = dados.get("cnpj","")
    story.append(Paragraph("Dados da Empresa", section_style))
    for item in [
        ("CNPJ",              cnpj_fmt),
        ("Razão Social",      dados.get("razao_social")),
        ("Nome Fantasia",     dados.get("nome_fantasia")),
        ("Situação",          dados.get("descricao_situacao_cadastral")),
        ("Data Abertura",     dados.get("data_inicio_atividade")),
        ("Natureza Jurídica", dados.get("natureza_juridica")),
        ("Porte",             dados.get("porte")),
        ("Capital Social",    f"R$ {dados.get('capital_social',0):,.2f}".replace(",","X").replace(".",",").replace("X",".") if dados.get("capital_social") else None),
        ("CNAE Principal",    f"{dados.get('cnae_fiscal','')} — {dados.get('cnae_fiscal_descricao','')}" if dados.get("cnae_fiscal") else None),
        ("Telefone",          dados.get("ddd_telefone_1")),
        ("E-mail",            dados.get("email")),
        ("Endereço",          ", ".join(filter(None,[dados.get("logradouro"), dados.get("numero"), dados.get("complemento"), dados.get("bairro"), dados.get("municipio"), dados.get("uf"), dados.get("cep")]))),
    ]:
        story += row(item[0], item[1])

    doc.build(story)
    return buf.getvalue()


def _gerar_pdf_qsa(dados: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    gold  = colors.HexColor("#b48c50")
    dark  = colors.HexColor("#1a1a2e")
    story = []

    h_title = ParagraphStyle("ht", fontName="Helvetica-Bold", fontSize=14, textColor=gold, leading=18)
    h_sub   = ParagraphStyle("hs", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#cccccc"), leading=14)
    section_style = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=11, textColor=gold, spaceBefore=14, spaceAfter=6)
    cell_style = ParagraphStyle("cel", fontName="Helvetica", fontSize=9, textColor=dark)
    head_style = ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)

    logo_path = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    logo_cell = RLImage(logo_path, width=2.2*cm, height=0.75*cm) if os.path.exists(logo_path) else Paragraph("VELINN", h_title)
    hdr = Table([[logo_cell, [Paragraph("QSA — Quadro de Sócios e Administradores", h_title),
                              Paragraph(dados.get("razao_social",""), h_sub)]]],
                colWidths=[3*cm, 14*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#0d1117")),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0),(-1,-1), 12), ("BOTTOMPADDING",(0,0),(-1,-1),12),
        ("LEFTPADDING",(0,0),(0,0),14), ("LEFTPADDING",(1,0),(1,0),12),
        ("LINEBELOW",  (0,0),(-1,-1),3, gold),
    ]))
    story += [hdr, Spacer(1, 16)]

    qsa = dados.get("qsa") or []
    if not qsa:
        story.append(Paragraph("Nenhum sócio encontrado.", cell_style))
    else:
        story.append(Paragraph("Composição Societária", section_style))
        table_data = [[
            Paragraph("Nome", head_style),
            Paragraph("Qualificação", head_style),
            Paragraph("Participação", head_style),
        ]]
        for socio in qsa:
            table_data.append([
                Paragraph(socio.get("nome_socio","—"), cell_style),
                Paragraph(socio.get("qualificacao_socio","—"), cell_style),
                Paragraph(socio.get("pais_origem","Brasil"), cell_style),
            ])
        t = Table(table_data, colWidths=[7*cm, 5*cm, 5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#0d1117")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f9f5ee"), colors.white]),
            ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("LINEBELOW",(0,0),(-1,-1),0.5, colors.HexColor("#e5e7eb")),
        ]))
        story.append(t)

    doc.build(story)
    return buf.getvalue()


def _drive_upload(folder_id: str, filename: str, content: bytes) -> str:
    if not DRIVE_SA_JSON or not folder_id:
        return ""
    try:
        sa_info = json.loads(DRIVE_SA_JSON)
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        meta = {"name": filename, "parents": [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/pdf")
        f = service.files().create(
            body=meta, media_body=media, fields="id,webViewLink",
            supportsAllDrives=True
        ).execute()
        link = f.get("webViewLink", "")
        print(f"[drive] upload OK: {link}")
        return link
    except Exception as e:
        print(f"[drive] FALHA: {e}")
        return ""


def _gerar_pdf(ficha: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    gold = colors.HexColor("#b48c50")
    dark = colors.HexColor("#1a1a2e")
    story = []

    section_style = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11,
                                    textColor=gold, spaceBefore=14, spaceAfter=6)
    label_style = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=9, textColor=dark)
    value_style = ParagraphStyle("value", fontName="Helvetica",      fontSize=9, textColor=dark)
    h_title = ParagraphStyle("ht", fontName="Helvetica-Bold", fontSize=14, textColor=gold, leading=18)
    h_sub   = ParagraphStyle("hs", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#cccccc"), leading=14)

    logo_path = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    logo_cell = RLImage(logo_path, width=2.2*cm, height=0.75*cm) if os.path.exists(logo_path) else Paragraph("VELINN", h_title)
    text_cell = [Paragraph("FICHA CADASTRAL VELINN", h_title), Paragraph(ficha.get("nome_pousada", ""), h_sub)]
    hdr = Table([[logo_cell, text_cell]], colWidths=[3*cm, 14*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#0d1117")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",  (0,0), (0,0), 14),
        ("LEFTPADDING",  (1,0), (1,0), 12),
        ("LINEBELOW",  (0,0), (-1,-1), 3, gold),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 12))

    def section(title, fields):
        story.append(Paragraph(title, section_style))
        rows = [[Paragraph(l, label_style), Paragraph(str(v or "—"), value_style)] for l, v in fields]
        t = Table(rows, colWidths=[5*cm, 12*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f5f0e8")),
            ("ROWBACKGROUNDS", (1,0), (1,-1), [colors.white, colors.HexColor("#fafafa")]),
            ("BOX",       (0,0), (-1,-1), 0.5, colors.HexColor("#e0d0b0")),
            ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#e8e0d0")),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ]))
        story.append(t)

    section("DADOS DA EMPRESA", [
        ("Razão Social",          ficha.get("razao_social")),
        ("Nome Fantasia",         ficha.get("nome_fantasia")),
        ("CNPJ",                  ficha.get("cnpj")),
        ("Endereço",              " ".join(filter(None, [ficha.get("endereco"), ficha.get("numero"), ficha.get("complemento")]))),
        ("Bairro",                ficha.get("bairro")),
        ("Cidade",                ficha.get("cidade")),
        ("Estado",                ficha.get("estado")),
        ("CEP",                   ficha.get("cep")),
        ("E-mail Administrativo", ficha.get("email_administrativo")),
    ])
    section("DADOS DO SÓCIO (assina o contrato)", [
        ("Nome",                 ficha.get("socio_nome")),
        ("Data de Nascimento",   ficha.get("socio_data_nascimento")),
        ("CPF",                  ficha.get("socio_cpf")),
        ("RG",                   ficha.get("socio_rg")),
        ("E-mail",               ficha.get("socio_email")),
        ("Celular",              ficha.get("socio_celular")),
        ("End. Residencial",     " ".join(filter(None, [ficha.get("socio_endereco"), ficha.get("socio_numero"), ficha.get("socio_complemento")]))),
    ])
    testemunhas = ficha.get("testemunhas") or []
    if isinstance(testemunhas, list) and testemunhas:
        for i, t in enumerate(testemunhas):
            lbl = f"TESTEMUNHA {i+1}" if len(testemunhas) > 1 else "DADOS DA TESTEMUNHA"
            section(lbl, [
                ("Nome",               t.get("nome")),
                ("Data de Nascimento", t.get("data_nascimento")),
                ("CPF",                t.get("cpf")),
                ("RG",                 t.get("rg")),
                ("E-mail",             t.get("email")),
            ])

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8))
    ts = ficha.get("preenchido_em", "")
    try:
        ts = datetime.fromisoformat(ts).strftime("%d/%m/%Y às %H:%M")
    except:
        pass
    story.append(Paragraph(f"Preenchido em: {ts} · VELINN Hotel",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
                        textColor=colors.HexColor("#999999"), alignment=TA_CENTER)))
    doc.build(story)
    return buf.getvalue()


@asynccontextmanager
async def lifespan(app):
    yield

app = FastAPI(title="VELINN Fichas", lifespan=lifespan)
BASE = os.path.join(os.path.dirname(__file__), "..")


@app.get("/logo")
def logo():
    return FileResponse(os.path.join(BASE, "logo.png"), media_type="image/png")

@app.get("/favicon.svg")
def favicon():
    return FileResponse(os.path.join(BASE, "favicon.svg"), media_type="image/svg+xml")


# ------------------------------------------------------------------
# PÚBLICO — formulário do cliente
# ------------------------------------------------------------------

@app.get("/cadastro/{token}")
def cadastro_page(token: str):
    rows = db_select("fichas_cadastrais", {"token": f"eq.{token}"})
    if not rows or not isinstance(rows, list):
        return JSONResponse({"error": "Link inválido"}, status_code=404)
    return FileResponse(os.path.join(BASE, "cadastro.html"))


@app.get("/api/cadastro/{token}")
def cadastro_info(token: str):
    rows = db_select("fichas_cadastrais", {"token": f"eq.{token}"})
    if not rows or not isinstance(rows, list):
        return JSONResponse({"ok": False, "msg": "Link inválido"}, status_code=404)
    f = rows[0]
    if f["status"] == "preenchido":
        return JSONResponse({"ok": False, "already": True, "msg": "Este formulário já foi preenchido."})
    return JSONResponse({"ok": True, "nome_pousada": f["nome_pousada"], "nome_proprietario": f["nome_proprietario"], "num_testemunhas": f.get("num_testemunhas", 1)})


@app.post("/api/cadastro/{token}/submeter")
async def submeter_ficha(token: str, request: Request):
    rows = db_select("fichas_cadastrais", {"token": f"eq.{token}"})
    if not rows or not isinstance(rows, list):
        return JSONResponse({"ok": False, "msg": "Link inválido"}, status_code=404)
    f = rows[0]
    if f["status"] == "preenchido":
        return JSONResponse({"ok": False, "msg": "Formulário já preenchido"}, status_code=400)
    body = await request.json()
    agora = datetime.now(timezone.utc).isoformat()
    update = {
        "status":                     "preenchido",
        "preenchido_em":              agora,
        "razao_social":               body.get("razao_social", ""),
        "nome_fantasia":              body.get("nome_fantasia", ""),
        "cnpj":                       body.get("cnpj", ""),
        "endereco":                   body.get("endereco", ""),
        "numero":                     body.get("numero", ""),
        "complemento":                body.get("complemento", ""),
        "bairro":                     body.get("bairro", ""),
        "cidade":                     body.get("cidade", ""),
        "estado":                     body.get("estado", ""),
        "cep":                        body.get("cep", ""),
        "email_administrativo":       body.get("email_administrativo", ""),
        "socio_nome":                 body.get("socio_nome", ""),
        "socio_data_nascimento":      body.get("socio_data_nascimento", ""),
        "socio_cpf":                  body.get("socio_cpf", ""),
        "socio_rg":                   body.get("socio_rg", ""),
        "socio_email":                body.get("socio_email", ""),
        "socio_celular":              body.get("socio_celular", ""),
        "socio_endereco":             body.get("socio_endereco", ""),
        "socio_numero":               body.get("socio_numero", ""),
        "socio_complemento":          body.get("socio_complemento", ""),
        "testemunhas":                body.get("testemunhas", []),
    }
    ok = db_update("fichas_cadastrais", update, {"token": f"eq.{token}"})
    if not ok:
        return JSONResponse({"ok": False, "msg": "Erro ao salvar"}, status_code=500)
    # Roda de forma síncrona para evitar que o Render mate o processo antes de concluir
    _pos_submissao({**f, **update})
    return JSONResponse({"ok": True})


def _pos_submissao(ficha: dict):
    print(f"[pos_submissao] iniciando para {ficha.get('nome_pousada')} / token={ficha.get('token','')[:8]}")
    print(f"[pos_submissao] drive_folder_id={ficha.get('drive_folder_id')} DRIVE_SA_JSON={'sim' if DRIVE_SA_JSON else 'NAO'} GMAIL_SA_JSON={'sim' if GMAIL_SA_JSON else 'NAO'}")

    try:
        pdf_bytes = _gerar_pdf(ficha)
        print(f"[pdf] gerado OK ({len(pdf_bytes)} bytes)")
    except Exception as e:
        print(f"[pdf] erro: {e}")
        pdf_bytes = None

    pdf_url = ""
    if pdf_bytes and ficha.get("drive_folder_id"):
        nome = f"Ficha_{ficha['nome_pousada'].replace(' ','_')}.pdf"
        pdf_url = _drive_upload(ficha["drive_folder_id"], nome, pdf_bytes)
        if pdf_url:
            db_update("fichas_cadastrais", {"pdf_drive_url": pdf_url}, {"token": f"eq.{ficha['token']}"})
    else:
        print(f"[drive] pulado — pdf_bytes={'sim' if pdf_bytes else 'nao'} folder='{ficha.get('drive_folder_id')}'")

    # Busca CNPJ e salva Cartão + QSA no Drive
    cnpj = ficha.get("cnpj", "")
    folder_id = ficha.get("drive_folder_id", "")
    cnpj_status = "⚠️ CNPJ não informado ou pasta não configurada"
    if cnpj and folder_id:
        try:
            dados_cnpj = _buscar_cnpj(cnpj)
            if dados_cnpj:
                svc = _drive_service_rw()
                if svc:
                    pasta_docs       = _drive_get_or_create_folder(svc, folder_id, "Documentos")
                    pasta_docs_hotel = _drive_get_or_create_folder(svc, pasta_docs, "Documentos Hotel")
                    cartao_bytes = _gerar_pdf_cartao_cnpj(dados_cnpj)
                    _drive_upload(pasta_docs_hotel, "CARTÃO CNPJ.pdf", cartao_bytes)
                    qsa_bytes = _gerar_pdf_qsa(dados_cnpj)
                    _drive_upload(pasta_docs_hotel, "QSA.pdf", qsa_bytes)
                    cnpj_status = "✅ Cartão CNPJ e QSA gerados e salvos no Drive"
                    print(f"[cnpj] {cnpj_status}")
                else:
                    cnpj_status = "❌ Erro: Drive não configurado"
            else:
                cnpj_status = f"❌ CNPJ {cnpj} não encontrado na Receita Federal"
        except Exception as e:
            cnpj_status = f"❌ Erro ao processar CNPJ: {e}"
            print(f"[cnpj] {cnpj_status}")

    _enviar_email_agradecimento(ficha)
    _enviar_email_notificacao(ficha, pdf_url, cnpj_status)
    print(f"[pos_submissao] concluído")


def _enviar_email_agradecimento(ficha: dict):
    email_link  = ficha.get("email_proprietario", "")
    email_socio = ficha.get("socio_email", "")
    nome    = ficha.get("nome_proprietario", "")
    pousada = ficha.get("nome_pousada", "")
    # deduplicate and filter empty
    destinatarios = list(dict.fromkeys(e for e in [email_link, email_socio] if e))
    if not destinatarios:
        return
    assunto = f"Ficha recebida com sucesso — {pousada}"
    plain = f"Olá, {nome}! Recebemos sua ficha cadastral de {pousada}. Em breve nossa equipe entrará em contato. VELINN Hotel"
    html = f"""
<div style="font-family:'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#ffffff;">
  <div style="background:#0d1117;padding:24px 32px;text-align:center;border-bottom:3px solid #b48c50;">
    <img src="https://velinn-fichas.onrender.com/logo" alt="VELINN Hotel" style="height:36px;" />
  </div>
  <div style="padding:32px;">
    <h2 style="color:#222;font-size:20px;">Ficha recebida com sucesso! ✓</h2>
    <p style="color:#555;line-height:1.6;">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6;">
      Recebemos a ficha cadastral de <strong>{pousada}</strong> com sucesso.
      Nossa equipe irá analisar as informações e em breve entrará em contato.
    </p>
    <p style="color:#555;line-height:1.6;">Obrigado pela confiança!</p>
  </div>
  <div style="background:#0d1117;padding:16px;text-align:center;border-top:3px solid #b48c50;">
    <p style="color:#888;font-size:11px;margin:0;">VELINN Hotel</p>
  </div>
</div>"""
    for dest in destinatarios:
        _enviar_email(dest, assunto, plain, html)


def _enviar_email_notificacao(ficha: dict, pdf_url: str, cnpj_status: str = ""):
    pousada      = ficha.get("nome_pousada", "")
    gerente_email = ficha.get("gerente_email", "")
    gerente_nome  = ficha.get("gerente_nome", "")
    ts = ficha.get("preenchido_em", "")
    try:
        ts = datetime.fromisoformat(ts).strftime("%d/%m/%Y às %H:%M")
    except:
        pass
    pdf_link = f'<a href="{pdf_url}" style="color:#b48c50;">Baixar PDF</a>' if pdf_url else "(Drive não configurado)"
    assunto = f"[Ficha Preenchida] {pousada}"
    plain = f"A ficha de {pousada} foi preenchida por {ficha.get('nome_proprietario','')} em {ts}. Gerente: {gerente_nome}. PDF: {pdf_url or 'não gerado'}"
    html = f"""
<div style="font-family:'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#ffffff;">
  <div style="background:#0d1117;padding:20px 32px;text-align:center;border-bottom:3px solid #b48c50;">
    <img src="https://velinn-fichas.onrender.com/logo" alt="VELINN Hotel" style="height:32px;display:block;margin:0 auto 8px;" />
    <span style="color:#b48c50;font-size:13px;font-weight:600;letter-spacing:1px;text-transform:uppercase;">Nova Ficha Cadastral</span>
  </div>
  <div style="padding:28px;">
    <p style="font-size:16px;color:#222;margin-bottom:20px;">
      <strong>{ficha.get('nome_proprietario','')}</strong> preencheu a ficha de <strong>{pousada}</strong>.
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;width:40%;">Pousada</td><td style="padding:8px;">{pousada}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">Proprietário</td><td style="padding:8px;">{ficha.get('nome_proprietario','')}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">E-mail</td><td style="padding:8px;">{ficha.get('email_proprietario','')}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">Gerente</td><td style="padding:8px;">{gerente_nome}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">Preenchido em</td><td style="padding:8px;">{ts}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">PDF</td><td style="padding:8px;">{pdf_link}</td></tr>
      <tr><td style="padding:8px;background:#f9f5ee;font-weight:600;">Captura CNPJ</td><td style="padding:8px;">{cnpj_status}</td></tr>
    </table>
    <p style="margin-top:20px;font-size:13px;color:#666;">
      Acesse o <a href="{HUB_URL}/fichas" style="color:#b48c50;">painel de fichas</a> para ver todos os detalhes.
    </p>
  </div>
</div>"""
    # Busca emails com notif_fichas=true do Hub
    hub_emails = []
    try:
        if HUB_URL and FICHAS_NOTIF_SECRET:
            r = req.get(f"{HUB_URL}/api/fichas/notif-emails",
                             headers={"X-Notif-Secret": FICHAS_NOTIF_SECRET}, timeout=5)
            if r.ok:
                hub_emails = r.json().get("emails", [])
    except Exception as e:
        print(f"[notif] erro ao buscar emails do Hub: {e}")

    destinatarios = list({gerente_email} | set(NOTIF_EMAILS) | set(hub_emails) - {""})
    for dest in destinatarios:
        _enviar_email(dest, assunto, plain, html)
