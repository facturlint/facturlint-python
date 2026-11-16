"""FacturLint CLI — Outil en ligne de commande pour auditer, réparer et certifier les factures Factur-X 1.09.2."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from facturlint_sdk import __version__
from facturlint_sdk.client import (
    FacturLintAPIError,
    FacturLintAuthError,
    FacturLintClient,
    FacturLintError,
    FacturLintPaymentRequiredError,
    FacturLintQuotaError,
    PRICING_URL,
)


def _format_status(status: str) -> str:
    badges = {
        "COMPLIANT": "✅ CONFORME (COMPLIANT)",
        "REPAIRABLE_ENVELOPE": "⚠️ ENVELOPPE RÉPARABLE (REPAIRABLE_ENVELOPE)",
        "BUSINESS_REJECTED": "❌ REJET MÉTIER / LÉGAL (BUSINESS_REJECTED)",
        "INVALID_FORMAT": "🚫 FORMAT INVALIDE (INVALID_FORMAT)",
    }
    return badges.get(status, status)


def _cmd_validate(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        report = client.validate(args.file)
    except FacturLintError as exc:
        print(f"Erreur validation FacturLint : {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("valid") else 1

    status = report.get("status", "UNKNOWN")
    container = report.get("container", {})
    inv = report.get("invoice_summary", {})
    issues = report.get("issues", [])
    maths = report.get("math_suggestions", [])

    print("=" * 70)
    print(f"FacturLint Audit — Factur-X 1.09.2 / EN 16931 / BR-FR-CTC")
    print("=" * 70)
    print(f"Fichier       : {args.file}")
    print(f"Statut        : {_format_status(status)}")
    print(f"Profil détecté: {container.get('detected_profile') or 'Non détecté'}")
    print(f"PDF/A-3b      : {'Oui' if container.get('is_pdfa3') else 'Non'}")
    print(f"Empreinte SHA : {report.get('sha256_fingerprint', '')[:16]}...")
    print(f"Temps calcul  : {report.get('processing_ms', 0)} ms (100% Stateless)")

    if inv.get("invoice_number") or inv.get("seller_name"):
        print("-" * 70)
        print("MÉTADONNÉES FACTURE :")
        if inv.get("invoice_number"):
            print(f"  • Numéro      : {inv.get('invoice_number')}")
        if inv.get("issue_date"):
            print(f"  • Date        : {inv.get('issue_date')}")
        if inv.get("seller_name"):
            print(f"  • Émetteur    : {inv.get('seller_name')} (SIREN: {inv.get('seller_siren_or_siret') or 'N/A'})")
        if inv.get("buyer_name"):
            print(f"  • Client      : {inv.get('buyer_name')} (SIREN: {inv.get('buyer_siren_or_siret') or 'N/A'})")
        if inv.get("grand_total"):
            print(f"  • Total TTC   : {inv.get('grand_total')} {inv.get('currency', 'EUR')}")

    if issues:
        print("-" * 70)
        print(f"ANOMALIES DÉTECTÉES ({len(issues)}) :")
        for idx, issue in enumerate(issues, 1):
            sev = issue.get("severity", "error").upper()
            code = issue.get("code", "UNKNOWN")
            msg = issue.get("message", "")
            raw_url = issue.get("doc_url") or f"/erreurs/{code}"
            doc_url = f"https://facturlint.com{raw_url}" if raw_url.startswith("/") else raw_url
            print(f"\n  [{idx}] [{sev}] {code}")
            print(f"      {msg}")
            if issue.get("fix_hint"):
                print(f"      💡 Solution : {issue.get('fix_hint')}")
            print(f"      🔗 Guide officiel : {doc_url}")

    if maths:
        print("-" * 70)
        print(f"ÉCARTS ARITHMÉTIQUES ({len(maths)}) :")
        for m in maths:
            print(f"  • {m.get('rule_code')} : {m.get('explanation')}")

    print("=" * 70)

    is_valid = bool(report.get("valid"))
    if not is_valid and status == "REPAIRABLE_ENVELOPE":
        print("\n💡 Conseil : cette anomalie d'enveloppe PDF/A-3b est auto-réparable sans altérer les montants.")
        print(f"   Exécutez : facturlint repair \"{args.file}\" -o conforme.pdf\n")

    if args.fail_on_warning and any(i.get("severity") == "warning" for i in issues):
        return 1

    return 0 if is_valid else 1


def _cmd_repair(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        res = client.repair(args.file, output_path=args.output)
    except (FacturLintPaymentRequiredError, FacturLintQuotaError) as exc:
        print(f"Erreur quota/abonnement : {exc.detail}", file=sys.stderr)
        print(f"Pour débloquer les réparations illimitées : {PRICING_URL}", file=sys.stderr)
        return 2
    except FacturLintError as exc:
        print(f"Erreur réparation FacturLint : {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("repaired") else 1

    repaired = res.get("repaired", False)
    actions = res.get("actions_applied", [])
    before_status = res.get("before_report", {}).get("status", "UNKNOWN")
    after_status = res.get("after_report", {}).get("status", "UNKNOWN")

    print("=" * 70)
    print("FacturLint Auto-Réparation PDF/A-3b")
    print("=" * 70)
    print(f"Fichier source : {args.file}")
    print(f"Statut avant   : {_format_status(before_status)}")
    print(f"Statut après   : {_format_status(after_status)}")
    print(f"Réussite       : {'Oui' if repaired else 'Non'}")
    if actions:
        print("\nActions appliquées sur l'enveloppe :")
        for a in actions:
            print(f"  ✓ {a}")
    if args.output:
        print(f"\nFacture conforme enregistrée dans : {args.output}")
    print(f"\nNotice légale : {res.get('legal_notice', '')}")
    print("=" * 70)

    return 0 if repaired else 1


def _cmd_certificate(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        raw_pdf = client.certificate(args.file, output_path=args.output)
    except FacturLintError as exc:
        print(f"Erreur génération attestation : {exc}", file=sys.stderr)
        return 2

    print(f"Attestation d'audit FacturLint générée avec succès ({len(raw_pdf)} octets).")
    print(f"Fichier : {args.output}")
    return 0


def _cmd_batch(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        res = client.batch_zip(
            args.zip_file,
            output_csv_path=args.csv,
            output_zip_path=args.out_zip,
        )
    except (FacturLintPaymentRequiredError, FacturLintQuotaError) as exc:
        print(f"Erreur quota/abonnement : {exc.detail}", file=sys.stderr)
        print(f"Le traitement par lot requiert un abonnement : {PRICING_URL}", file=sys.stderr)
        return 2
    except FacturLintError as exc:
        print(f"Erreur audit par lot : {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    summary = res.get("summary", {})
    print("=" * 70)
    print("FacturLint — Audit Groupé par Lot .ZIP")
    print("=" * 70)
    print(f"Archive traitée    : {args.zip_file}")
    print(f"Factures analysées : {summary.get('total_files', 0)}")
    print(f"Conformes d'origine: {summary.get('compliant_initial', 0)}")
    print(f"Auto-réparées      : {summary.get('auto_repaired', 0)}")
    print(f"Conformes final    : {summary.get('compliant_final', 0)}")
    print(f"Rejets métier      : {summary.get('rejected_business', 0)}")
    print(f"Formats invalides  : {summary.get('invalid_format', 0)}")
    print(f"Temps traitement   : {summary.get('processing_ms', 0)} ms")

    if args.csv:
        print(f"\nRapport Excel CSV enregistré : {args.csv}")
    if args.out_zip:
        print(f"Archive factures réparées    : {args.out_zip}")
    print("=" * 70)

    return 0


def _cmd_quota(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        quota_data = client.quota()
    except FacturLintAuthError:
        print(
            "Erreur : Clé API manquante ou invalide. Définissez FACTURLINT_API_KEY ou utilisez --api-key.\n"
            f"Obtenez votre clé sur {PRICING_URL}",
            file=sys.stderr,
        )
        return 2
    except FacturLintError as exc:
        print(f"Erreur consultation quota : {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(quota_data, ensure_ascii=False, indent=2))
        return 0

    print("=" * 60)
    print("FacturLint — Quota & Formule API")
    print("=" * 60)
    print(f"Formule          : {str(quota_data.get('plan', '')).upper()}")
    print(f"Préfixe clé      : {quota_data.get('key_prefix', 'N/A')}")
    print(f"Quota mensuel    : {quota_data.get('monthly_quota', 0)} factures")
    print(f"Utilisé ce mois  : {quota_data.get('used_this_month', 0)}")
    print(f"Restant ce mois  : {quota_data.get('remaining_this_month', 0)}")
    print(f"Max factures/lot : {quota_data.get('max_batch_files', 20)}")
    print("=" * 60)
    return 0


def _cmd_rules(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        rules = client.list_rules(category=args.category)
    except FacturLintError as exc:
        print(f"Erreur consultation catalogue : {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rules, ensure_ascii=False, indent=2))
        return 0

    print(f"FacturLint — Catalogue des règles ({len(rules)} règles répertoriées)\n")
    for r in rules:
        code = r.get("code")
        title = r.get("title")
        cat = r.get("category")
        repairable = " [Auto-réparable]" if r.get("auto_repairable") else ""
        print(f"• {code:<20} [{cat}] {title}{repairable}")
        print(f"  Guide : https://facturlint.com/erreurs/{code}")
    return 0


def _cmd_embed(client: FacturLintClient, args: argparse.Namespace) -> int:
    try:
        raw_pdf = client.embed(args.pdf, args.xml, output_path=args.output)
    except FacturLintError as exc:
        print(f"Erreur encapsulation Factur-X : {exc}", file=sys.stderr)
        return 2

    print(f"Facture hybride Factur-X générée avec succès ({len(raw_pdf)} octets).")
    print(f"Fichier : {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="facturlint",
        description="FacturLint CLI — Audit & Auto-Réparation Factur-X 1.09.2 / EN 16931 / BR-FR-CTC.",
        epilog="Documentation et clés API disponibles sur https://facturlint.com",
    )
    parser.add_argument("-v", "--version", action="version", version=f"facturlint {__version__}")
    parser.add_argument("-k", "--api-key", help="Clé API FacturLint (ou variable FACTURLINT_API_KEY)")
    parser.add_argument(
        "--base-url",
        default=os.getenv("FACTURLINT_BASE_URL", "https://facturlint.com"),
        help="URL de l'API FacturLint (défaut : https://facturlint.com)",
    )
    parser.add_argument("--json", action="store_true", help="Affichage brut au format JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate
    p_val = subparsers.add_parser("validate", help="Valider une facture PDF Factur-X ou XML CII")
    p_val.add_argument("file", help="Chemin du fichier PDF ou XML à auditer")
    p_val.add_argument("--fail-on-warning", action="store_true", help="Retourner code 1 même pour de simples warnings")

    # repair
    p_rep = subparsers.add_parser("repair", help="Auto-réparer l'enveloppe technique PDF/A-3b")
    p_rep.add_argument("file", help="Chemin du PDF Factur-X défectueux")
    p_rep.add_argument("-o", "--output", required=True, help="Chemin où enregistrer le PDF conforme réparé")

    # cert
    p_cert = subparsers.add_parser("certificate", aliases=["cert"], help="Générer l'attestation PDF d'audit")
    p_cert.add_argument("file", help="Chemin du fichier PDF ou XML")
    p_cert.add_argument("-o", "--output", required=True, help="Chemin où enregistrer l'attestation PDF")

    # batch
    p_bat = subparsers.add_parser("batch", help="Auditer et réparer un lot complet de factures (.ZIP)")
    p_bat.add_argument("zip_file", help="Chemin de l'archive .ZIP")
    p_bat.add_argument("--csv", help="Chemin où enregistrer le rapport Excel CSV")
    p_bat.add_argument("--out-zip", help="Chemin où enregistrer l'archive des factures réparées")

    # quota
    subparsers.add_parser("quota", help="Consulter le solde restant et la formule API active")

    # rules
    p_rules = subparsers.add_parser("rules", help="Consulter le catalogue des règles normatives")
    p_rules.add_argument("--category", help="Filtrer par catégorie (ex: schematron_br_fr, pdfa3_xmp)")

    # embed
    p_emb = subparsers.add_parser("embed", help="Encapsuler un XML Factur-X dans un PDF pour créer un PDF/A-3b")
    p_emb.add_argument("--pdf", required=True, help="Facture visuelle PDF")
    p_emb.add_argument("--xml", required=True, help="Flux XML Factur-X 1.09.2")
    p_emb.add_argument("-o", "--output", required=True, help="PDF Factur-X résultant")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = FacturLintClient(api_key=args.api_key, base_url=args.base_url)

    cmd_map = {
        "validate": _cmd_validate,
        "repair": _cmd_repair,
        "certificate": _cmd_certificate,
        "cert": _cmd_certificate,
        "batch": _cmd_batch,
        "quota": _cmd_quota,
        "rules": _cmd_rules,
        "embed": _cmd_embed,
    }

    handler = cmd_map.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(2)

    code = handler(client, args)
    sys.exit(code)


if __name__ == "__main__":
    main()
