"""FacturLint Official Python SDK — Pure stdlib client for Factur-X 1.09.2 & EN 16931 compliance."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, BinaryIO
import urllib.error
import urllib.parse
import urllib.request
import uuid

SDK_VERSION = "0.2.0"
DEFAULT_BASE_URL = "https://facturlint.com"
PRICING_URL = "https://facturlint.com/#tarifs"


# --- Custom Exceptions ---


class FacturLintError(Exception):
    """Base exception for all FacturLint SDK errors."""


class FacturLintAPIError(FacturLintError):
    """Raised when the FacturLint API returns an HTTP error code."""

    def __init__(
        self,
        status_code: int,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.code = self.payload.get("code")
        self.detail = self.payload.get("detail", message)


class FacturLintAuthError(FacturLintAPIError):
    """Raised on HTTP 401 Unauthorized (missing or invalid API key)."""


class FacturLintPaymentRequiredError(FacturLintAPIError):
    """Raised on HTTP 402 Payment Required (quota plan limit or batch subscription needed)."""


class FacturLintQuotaError(FacturLintAPIError):
    """Raised on HTTP 429 Too Many Requests (daily anonymous limit or monthly quota exhausted)."""


# --- Pure stdlib Multipart Form-Data encoder (RFC 7578) ---


def encode_multipart_formdata(
    fields: dict[str, str] | None = None,
    files: list[tuple[str, str, bytes, str | None]] | None = None,
) -> tuple[bytes, str]:
    """Encodes form fields and binary files into an RFC 7578 multipart/form-data payload.

    Args:
        fields: Mapping of form field name to string value.
        files: List of tuples (field_name, filename, file_bytes, optional_content_type).

    Returns:
        A tuple of (encoded_body_bytes, content_type_header_with_boundary).
    """
    boundary = f"----FacturLintFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    if fields:
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

    if files:
        for field_name, filename, content, content_type in files:
            ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            clean_filename = Path(filename).name.replace('"', '\\"')
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{clean_filename}"\r\n'.encode(
                    "utf-8"
                )
            )
            body.extend(f"Content-Type: {ct}\r\n\r\n".encode("utf-8"))
            body.extend(content)
            body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type_header


def _read_file_payload(
    file_input: str | Path | bytes | BinaryIO,
    default_name: str,
    custom_name: str | None = None,
) -> tuple[str, bytes]:
    """Reads file input into a (filename, bytes) pair."""
    if isinstance(file_input, (str, Path)):
        p = Path(file_input)
        if not p.is_file():
            raise FileNotFoundError(f"Le fichier spécifié n'existe pas : {p}")
        return custom_name or p.name, p.read_bytes()

    if isinstance(file_input, bytes):
        return custom_name or default_name, file_input

    if hasattr(file_input, "read"):
        name = custom_name or getattr(file_input, "name", default_name)
        data = file_input.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return Path(str(name)).name, data

    raise TypeError(
        f"Format de fichier non pris en charge : {type(file_input)}. "
        "Attendu : str, pathlib.Path, bytes ou objet fichier binaire."
    )


# --- Client Class ---


class FacturLintClient:
    """Official stateless Python client for the FacturLint Factur-X & BR-FR-CTC compliance API.

    Uses Python standard library only (no external dependencies).
    Compatible with Python 3.9+.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Initializes the FacturLint client.

        Args:
            api_key: Optional API key (defaults to environment variable FACTURLINT_API_KEY).
                     Validation is free without a key. Auto-repair and batch require a key or paid plan.
            base_url: Optional API root URL (defaults to FACTURLINT_BASE_URL or https://facturlint.com).
            timeout: Network request timeout in seconds (default 60s).
        """
        self.api_key = api_key or os.getenv("FACTURLINT_API_KEY")
        resolved_base = base_url or os.getenv("FACTURLINT_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = resolved_base.rstrip("/")
        self.timeout = timeout

    def _build_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> urllib.request.Request:
        url = f"{self.base_url}{endpoint}"
        req_headers = {
            "User-Agent": f"facturlint-python-sdk/{SDK_VERSION}",
            "Accept": "application/json, application/pdf, */*",
        }
        if self.api_key:
            req_headers["X-API-Key"] = self.api_key
            req_headers["Authorization"] = f"Bearer {self.api_key}"

        if headers:
            req_headers.update(headers)

        return urllib.request.Request(url=url, data=data, headers=req_headers, method=method)

    def _execute(
        self,
        endpoint: str,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        req = self._build_request(endpoint, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                raw_bytes = resp.read()
                return status, resp_headers, raw_bytes
        except urllib.error.HTTPError as exc:
            raw_err = exc.read()
            err_payload: dict[str, Any] = {}
            try:
                err_payload = json.loads(raw_err.decode("utf-8"))
            except Exception:
                err_payload = {"detail": raw_err.decode("utf-8", errors="replace")}

            msg = err_payload.get("detail") or f"Erreur API FacturLint HTTP {exc.code} : {exc.reason}"

            if exc.code == 401:
                raise FacturLintAuthError(
                    status_code=401,
                    message=f"Authentification FacturLint échouée (401) : {msg}",
                    payload=err_payload,
                ) from exc
            if exc.code == 402:
                upgrade_tip = f"\nPour débloquer ou augmenter votre quota : {PRICING_URL}"
                raise FacturLintPaymentRequiredError(
                    status_code=402,
                    message=f"Abonnement ou quota requis (402) : {msg}{upgrade_tip}",
                    payload=err_payload,
                ) from exc
            if exc.code == 429:
                upgrade_tip = f"\nQuota mensuel épuisé. Passez à la formule supérieure : {PRICING_URL}"
                raise FacturLintQuotaError(
                    status_code=429,
                    message=f"Limite de requêtes atteinte (429) : {msg}{upgrade_tip}",
                    payload=err_payload,
                ) from exc

            raise FacturLintAPIError(
                status_code=exc.code,
                message=f"Erreur HTTP {exc.code} FacturLint : {msg}",
                payload=err_payload,
            ) from exc
        except urllib.error.URLError as exc:
            raise FacturLintError(
                f"Impossible de joindre le serveur FacturLint sur {self.base_url} : {exc.reason}"
            ) from exc

    def validate(
        self,
        file: str | Path | bytes | BinaryIO,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Validates a Factur-X PDF or CII XML invoice against EN 16931 & BR-FR-CTC rules.

        Free & stateless endpoint. No invoice is ever stored.

        Args:
            file: Path to invoice file, raw bytes, or readable file object.
            filename: Optional custom filename.

        Returns:
            Validation report dictionary matching the official FacturLint ValidationReport schema.
        """
        fname, content = _read_file_payload(file, "facture.pdf", filename)
        body, ct = encode_multipart_formdata(files=[("file", fname, content, None)])
        _, _, raw_resp = self._execute("/v1/validate", method="POST", data=body, headers={"Content-Type": ct})
        return json.loads(raw_resp.decode("utf-8"))

    def repair(
        self,
        file: str | Path | bytes | BinaryIO,
        output_path: str | Path | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Automatically repairs PDF/A-3b envelope issues (XMP metadata, ICC sRGB color profile, attachments).

        Guaranteed zero accounting alteration: amounts, taxes and lines are strictly preserved.

        Args:
            file: Path to defective PDF, bytes, or file object.
            output_path: Optional path where to write the repaired compliant PDF.
            filename: Optional custom filename.

        Returns:
            RepairResult dictionary containing before_report, after_report, and actions_applied.
        """
        fname, content = _read_file_payload(file, "facture.pdf", filename)
        body, ct = encode_multipart_formdata(files=[("file", fname, content, None)])
        _, _, raw_resp = self._execute("/v1/repair", method="POST", data=body, headers={"Content-Type": ct})
        res: dict[str, Any] = json.loads(raw_resp.decode("utf-8"))

        if output_path and res.get("repaired_pdf_base64"):
            repaired_bytes = base64.b64decode(res["repaired_pdf_base64"])
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(repaired_bytes)

        return res

    def certificate(
        self,
        file: str | Path | bytes | BinaryIO,
        output_path: str | Path | None = None,
        filename: str | None = None,
    ) -> bytes:
        """Generates an official audit certificate PDF for an invoice (hash SHA-256 + compliance proof).

        Args:
            file: Path to invoice, bytes, or file object.
            output_path: Optional path where to write the certificate PDF.
            filename: Optional custom filename.

        Returns:
            Binary bytes of the official audit certificate PDF.
        """
        fname, content = _read_file_payload(file, "facture.pdf", filename)
        body, ct = encode_multipart_formdata(files=[("file", fname, content, None)])
        _, _, raw_pdf = self._execute("/v1/certificate", method="POST", data=body, headers={"Content-Type": ct})

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(raw_pdf)

        return raw_pdf

    def batch_zip(
        self,
        zip_file: str | Path | bytes | BinaryIO,
        output_csv_path: str | Path | None = None,
        output_zip_path: str | Path | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Audits an entire .ZIP archive of invoices, with auto-repair and Excel CSV generation.

        Stateless execution in RAM. Requires an active FacturLint plan (Starter, Pro, Cabinet).

        Args:
            zip_file: Path to .ZIP archive, bytes, or file object.
            output_csv_path: Optional path to save the generated Excel CSV report.
            output_zip_path: Optional path to save the .ZIP archive containing repaired invoices.
            filename: Optional custom filename.

        Returns:
            Dictionary with batch audit summary, individual invoice items, and quota info.
        """
        fname, content = _read_file_payload(zip_file, "lot_factures.zip", filename)
        body, ct = encode_multipart_formdata(files=[("file", fname, content, "application/zip")])
        _, _, raw_resp = self._execute("/v1/batch", method="POST", data=body, headers={"Content-Type": ct})
        res: dict[str, Any] = json.loads(raw_resp.decode("utf-8"))

        if output_csv_path and res.get("csv_report_base64"):
            csv_bytes = base64.b64decode(res["csv_report_base64"])
            csv_p = Path(output_csv_path)
            csv_p.parent.mkdir(parents=True, exist_ok=True)
            csv_p.write_bytes(csv_bytes)

        if output_zip_path and res.get("repaired_zip_base64"):
            zip_bytes = base64.b64decode(res["repaired_zip_base64"])
            zip_p = Path(output_zip_path)
            zip_p.parent.mkdir(parents=True, exist_ok=True)
            zip_p.write_bytes(zip_bytes)

        return res

    def embed(
        self,
        pdf_file: str | Path | bytes | BinaryIO,
        xml_file: str | Path | bytes | BinaryIO,
        output_path: str | Path | None = None,
        pdf_filename: str | None = None,
        xml_filename: str | None = None,
    ) -> bytes:
        """Embeds a Factur-X CII XML stream into an existing visual PDF to create a PDF/A-3b hybrid invoice.

        Requires an API key.

        Args:
            pdf_file: Visual PDF document.
            xml_file: Factur-X 1.09.2 XML CII stream.
            output_path: Optional destination path for the hybrid PDF.
            pdf_filename: Optional custom name for the PDF.
            xml_filename: Optional custom name for the XML.

        Returns:
            Binary bytes of the compliant Factur-X hybrid PDF.
        """
        p_name, p_bytes = _read_file_payload(pdf_file, "facture.pdf", pdf_filename)
        x_name, x_bytes = _read_file_payload(xml_file, "factur-x.xml", xml_filename)
        body, ct = encode_multipart_formdata(
            files=[
                ("pdf", p_name, p_bytes, "application/pdf"),
                ("xml", x_name, x_bytes, "application/xml"),
            ]
        )
        _, _, raw_pdf = self._execute("/v1/embed", method="POST", data=body, headers={"Content-Type": ct})

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(raw_pdf)

        return raw_pdf

    def quota(self) -> dict[str, Any]:
        """Retrieves remaining API quota, current plan, and batch limits for the authenticated key.

        Returns:
            Quota dictionary (plan, monthly_quota, used_this_month, remaining_this_month, max_batch_files).
        """
        _, _, raw_resp = self._execute("/v1/quota", method="GET")
        return json.loads(raw_resp.decode("utf-8"))

    def list_rules(self, category: str | None = None) -> list[dict[str, Any]]:
        """Retrieves the complete catalog of Factur-X, EN 16931 and BR-FR-CTC normative rules.

        Args:
            category: Optional filter (ex: 'schematron_br_fr', 'schematron_en16931', 'pdfa3_xmp').

        Returns:
            List of rule definitions with explanation, severity, and resolution hints.
        """
        endpoint = "/v1/rules"
        if category:
            endpoint = f"{endpoint}?category={urllib.parse.quote(category)}"
        _, _, raw_resp = self._execute(endpoint, method="GET")
        return json.loads(raw_resp.decode("utf-8"))
