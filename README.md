# FacturLint — Factur-X 1.09.2, EN 16931 & BR-FR-CTC Python SDK & CLI

[![PyPI version](https://img.shields.io/pypi/v/facturlint.svg)](https://pypi.org/project/facturlint/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://pypi.org/project/facturlint/)
[![Stateless](https://img.shields.io/badge/privacy-100%25%20stateless-green.svg)](https://facturlint.com)
[![Factur-X](https://img.shields.io/badge/norm-Factur--X%201.09.2-orange.svg)](https://facturlint.com/docs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FacturLint** est le SDK Python officiel et l'outil CLI pour valider, certifier et réparer automatiquement les factures électroniques **Factur-X 1.09.2**, **EN 16931** et **BR-FR-CTC** (Réforme française 2026 de la facturation électronique, Chorus Pro et Plateformes Agréées / PDP).

Conçu sans aucune dépendance tierce (*Pure Python Standard Library*), FacturLint s'intègre en 2 minutes dans vos pipelines CI/CD, ERP, logiciels de facturation, outils comptables et agents IA via le [Serveur MCP FacturLint](https://facturlint.com/mcp).

- 🌐 Site officiel : [https://facturlint.com](https://facturlint.com)
- 📚 Documentation API : [https://facturlint.com/docs](https://facturlint.com/docs)
- 🔍 Catalogue des 110+ règles d'erreurs : [https://facturlint.com/erreurs](https://facturlint.com/erreurs)
- 🤖 Serveur MCP & Agent IA : [https://facturlint.com/mcp](https://facturlint.com/mcp)
- 💳 Tarifs & Clés API : [https://facturlint.com/#tarifs](https://facturlint.com/#tarifs)

---

## ⚡ Points forts

- **100 % Déterministe & Stateless** : Aucune facture ni donnée fiscale n'est stockée en base de données (zéro rétention, conformité RGPD absolue).
- **Zéro dépendance d'exécution** : Fonctionne avec Python 3.9+ standard (`urllib`, `json`, `pathlib`). Aucun binaire C lourd à installer.
- **Validation multicouche complète** :
  - Enveloppe physique PDF/A-3b (ISO 19005-3)
  - Métadonnées XMP Factur-X (`fx:ConformanceLevel`, `fx:DocumentFileName`, `fx:Version`)
  - Profil colorimétrique ICC sRGB (`OutputIntent`)
  - Schémas XML W3C XSD officiels UN/CEFACT CII D16B
  - Schematron européen CEN/TC 434 (Norme EN 16931-1)
  - Règles spécifiques françaises BR-FR-CTC (DGFIP / AIFE)
  - Audit d'intégrité arithmétique (HT + TVA = TTC)
- **Auto-réparation chirurgicale d'enveloppe** : Corrige les défauts techniques d'enveloppe PDF/A-3b en garantissant zéro altération des montants ni des mentions comptables.
- **Audit groupé par lot .ZIP** : Traitement en RAM avec rapport Excel CSV structuré pour les cabinets d'expertise comptable.

---

## 📦 Installation

```bash
pip install facturlint
```

Aucun paquet tiers n'est requis. Fonctionne instantanément sous Linux, Windows et macOS.

---

## 🚀 Utilisation en Ligne de Commande (CLI)

Une fois installé, le binaire `facturlint` est disponible dans votre terminal :

### 1. Valider une facture (Gratuit & Stateless)

```bash
facturlint validate facture.pdf
```

Pour les pipelines CI/CD (ex: GitHub Actions), activez l'échec strict sur simple avertissement :
```bash
facturlint validate facture.pdf --fail-on-warning
```

Export au format JSON pour script shell :
```bash
facturlint validate facture.pdf --json
```

### 2. Auto-réparer l'enveloppe technique PDF/A-3b

Répare le profil ICC sRGB manquant, l'en-tête XMP Factur-X ou le dictionnaire AFRelationship sans toucher au corps de la facture :

```bash
facturlint repair facture_rejetee.pdf -o facture_conforme.pdf
```

### 3. Générer l'attestation officielle d'audit PDF

Produit une attestation infalsifiable avec empreinte SHA-256 certifiant la conformité au moment du contrôle :

```bash
facturlint cert facture.pdf -o attestation_audit.pdf
```

### 4. Traiter un lot complet de factures (.ZIP)

Idéal pour les experts-comptables et DAF traitant des centaines de factures mensuelles :

```bash
facturlint batch factures_mois.zip --csv rapport_excel.csv --out-zip factures_reparees.zip
```

### 5. Consulter le quota de votre clé API

```bash
export FACTURLINT_API_KEY="fl_live_votre_cle_ici"
facturlint quota
```

### 6. Consulter le catalogue des 110+ règles normatives

```bash
facturlint rules --category schematron_br_fr
```

Chaque anomalie renvoie vers une fiche détaillée sur [https://facturlint.com/erreurs/{code}](https://facturlint.com/erreurs).

---

## 💻 Utilisation comme SDK Python

### Validation simple (sans clé API)

```python
from facturlint_sdk import FacturLintClient

client = FacturLintClient()

# Audit d'une facture Factur-X (PDF ou XML CII)
report = client.validate("facture.pdf")

if report["valid"]:
    print(f"Facture conforme ! Profil : {report['container']['detected_profile']}")
    print(f"Total TTC : {report['invoice_summary']['grand_total']} EUR")
else:
    print(f"Statut : {report['status']}")
    for issue in report["issues"]:
        print(f"[{issue['severity'].upper()}] {issue['code']} : {issue['message']}")
        print(f"👉 Guide résolution : https://facturlint.com/erreurs/{issue['code']}")
```

### Auto-réparation PDF/A-3b & Export

```python
from facturlint_sdk import FacturLintClient

client = FacturLintClient(api_key="fl_live_votre_cle")

# Répare l'enveloppe et écrit directement le fichier PDF conforme
result = client.repair("facture_defectueuse.pdf", output_path="facture_reparee.pdf")

if result["repaired"]:
    print("Enveloppe PDF/A-3b réparée avec succès !")
    for action in result["actions_applied"]:
        print(f" - {action}")
```

### Audit groupé par lot .ZIP (Pour cabinets comptables)

```python
from facturlint_sdk import FacturLintClient

client = FacturLintClient(api_key="fl_live_votre_cle")

batch_res = client.batch_zip(
    "lot_novembre.zip",
    output_csv_path="rapport_audit.csv",
    output_zip_path="lot_novembre_repare.zip",
)

summary = batch_res["summary"]
print(f"Total analysé       : {summary['total_files']}")
print(f"Conformes d'origine : {summary['compliant_initial']}")
print(f"Auto-réparées       : {summary['auto_repaired']}")
print(f"Rejets métier       : {summary['rejected_business']}")
```

### Génération d'attestation PDF certifiée

```python
from facturlint_sdk import FacturLintClient

client = FacturLintClient()
pdf_bytes = client.certificate("facture.pdf", output_path="attestation.pdf")
print(f"Attestation générée ({len(pdf_bytes)} octets).")
```

---

## 🤖 Intégration Agents IA & MCP (Model Context Protocol)

FacturLint expose un serveur **Model Context Protocol** natif pour Claude Desktop, Cursor, Copilot, LangChain et AutoGen.

Configurez votre client MCP en ajoutant simplement :

```json
{
  "mcpServers": {
    "facturlint": {
      "url": "https://facturlint.com/mcp",
      "headers": {
        "X-API-Key": "fl_live_votre_cle_optionnelle"
      }
    }
  }
}
```

Documentation complète MCP : [https://facturlint.com/mcp](https://facturlint.com/mcp) et [Agent Card](https://facturlint.com/.well-known/agent-card.json).

---

## 🛠️ Matrice des Profils Factur-X Supportés

| Profil Factur-X | Description | Usage typique |
| :--- | :--- | :--- |
| **MINIMUM** | Données d'en-tête et pied de facture | Facturation B2C / Archivage |
| **BASIC WL** | Données d'en-tête sans détail de lignes | Pré-comptabilité |
| **BASIC** | Facture avec détail de lignes standard | Facturation B2B courante |
| **EN 16931** | Norme européenne complète | Marchés publics, Chorus Pro, B2B FR |
| **EXTENDED** | Données sectorielles enrichies (BTP, négoce) | Facturation complexe |

FacturLint vérifie également les extensions françaises **BR-FR-CTC** requises par la réforme 2026 (numéros de SIRET, catégories d'opérations, options de TVA).

---

## 📄 Licence & Mentions

Distribué sous licence **MIT**.
Édité par **FacturLint** — [https://facturlint.com](https://facturlint.com).
Support & Contact : `contact@facturlint.com`.
Consultez notre [documentation technique](https://facturlint.com/docs) et notre [catalogue de règles](https://facturlint.com/erreurs).
