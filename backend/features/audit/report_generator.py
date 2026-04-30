import asyncio
import hashlib
import os
import shutil
import tempfile
from datetime import UTC, datetime

from .integrity_checker import IntegrityReport
from .trail import ProvenanceRecord


class ReportGenerator:

    def _escape_latex(self, text: str) -> str:
        if not isinstance(text, str):
            text = str(text)
        text = text.replace("\\", "\\textbackslash{}")
        special_chars = {
            "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#",
            "_": "\\_", "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}",
            "^": "\\textasciicircum{}"
        }
        for char, escape in special_chars.items():
            text = text.replace(char, escape)
        return text

    async def _compile_latex(self, tex_content: str) -> bytes:
        tmpdir = tempfile.mkdtemp()
        try:
            tex_file = os.path.join(tmpdir, "report.tex")
            with open(tex_file, "w", encoding="utf-8") as f:  # noqa: ASYNC230
                f.write(tex_content)

            try:
                proc = await asyncio.create_subprocess_exec(
                    "pdflatex", "-interaction=nonstopmode", "-output-directory", tmpdir, tex_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except FileNotFoundError as exc:
                raise FileNotFoundError("pdflatex non trouvé — installer texlive-full sur la VM Ubuntu") from exc

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except TimeoutError as exc:
                proc.kill()
                raise RuntimeError("Timeout pdflatex (30s) atteint") from exc

            if proc.returncode != 0:
                log_lines = stdout.decode("utf-8", errors="replace").split("\n")[-20:]
                log_err = "\n".join(log_lines)
                raise RuntimeError(f"Erreur compilation pdflatex (code {proc.returncode}):\n{log_err}")

            pdf_file = os.path.join(tmpdir, "report.pdf")
            if not os.path.exists(pdf_file) or os.path.getsize(pdf_file) == 0:
                raise RuntimeError("PDF généré vide — vérifier le template LaTeX")

            with open(pdf_file, "rb") as f:  # noqa: ASYNC230
                return f.read()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _build_tex(self, asset_id: str, asset_state: dict, provenance: list[ProvenanceRecord], integrity: IntegrityReport, generated_by: str, doc_hash: str) -> str:
        esc_asset_id = self._escape_latex(asset_id)
        esc_asset_name = self._escape_latex(asset_state.get("asset_name", "N/A"))
        esc_isin = self._escape_latex(asset_state.get("isin", "N/A"))
        esc_lei = self._escape_latex(asset_state.get("issuer_lei", "N/A"))

        val_nom = asset_state.get("nominal_value", 0)
        str_val = f"{float(val_nom):,.2f}".replace(",", " ")
        esc_str_val = self._escape_latex(str_val)

        esc_status = self._escape_latex(asset_state.get("status", "N/A"))
        status_color = r"\textcolor{red}{\textbf{" + esc_status + r"}}" if esc_status == "GELE" else r"\textcolor{green!60!black}{\textbf{" + esc_status + r"}}"

        gen_date = datetime.now(UTC).strftime("%d/%m/%Y %H:%M:%S UTC")
        esc_gen_date = self._escape_latex(gen_date)
        esc_gen_by = self._escape_latex(generated_by)
        esc_hash = self._escape_latex(doc_hash)

        prov_rows = []
        for idx, rec in enumerate(provenance):
            dn_raw = rec.actor_dn[:45] + "..." if len(rec.actor_dn) > 45 else rec.actor_dn
            just_raw = rec.justification[:40] + "..." if len(rec.justification) > 40 else rec.justification

            num = str(idx + 1)
            dt_str = self._escape_latex(rec.timestamp.strftime("%d/%m/%Y %H:%M:%S"))
            act = self._escape_latex(rec.action)
            msp = self._escape_latex(rec.actor_msp)
            dn = self._escape_latex(dn_raw)
            amt = f"{rec.amount:,.2f}".replace(",", " ") if rec.amount > 0 else "--"
            esc_amt = self._escape_latex(amt)
            just = self._escape_latex(just_raw)

            rowcol = ""
            if rec.action == "TOKENISE":
                rowcol = r"\rowcolor[rgb]{0.88,0.96,0.88}"
            elif rec.action == "TRANSFERE":
                rowcol = r"\rowcolor[rgb]{0.88,0.92,0.98}"
            elif rec.action == "GELE":
                rowcol = r"\rowcolor[rgb]{0.98,0.88,0.88}"
            elif rec.action == "DEGELE":
                rowcol = r"\rowcolor[rgb]{0.98,0.96,0.88}"

            prov_rows.append(f"{rowcol} {num} & {dt_str} & {act} & {msp} & {dn} & {esc_amt} & {just} \\\\")

        prov_table_body = "\n".join(prov_rows)

        g_valid = integrity.valid
        st_global = r"\textcolor{green!60!black}{\textbf{VALIDE}}" if g_valid else r"\textcolor{red}{\textbf{ALTÉRÉ}}"

        int_rows = []
        for rec in integrity.records:
            tx_raw = rec.tx_id[:16] + "..." if len(rec.tx_id) > 16 else rec.tx_id
            hash_raw = rec.computed_hash[:24] + "..." if len(rec.computed_hash) > 24 else rec.computed_hash
            esc_tx = self._escape_latex(tx_raw)
            esc_hash_val = self._escape_latex(hash_raw)

            st = r"\textcolor{green!60!black}{\textbf{VALIDE}}" if rec.valid else r"\textcolor{red}{\textbf{ALTÉRÉ}}"
            int_rows.append(f"{rec.record_index + 1} & \\texttt{{{esc_tx}}} & \\texttt{{{esc_hash_val}}} & {st} \\\\")

        int_table_body = "\n".join(int_rows)
        int_total = len(integrity.records)

        tex = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[french]{babel}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{longtable}
\usepackage{array}
\usepackage[table]{xcolor}
\usepackage{fancyhdr}
\usepackage[colorlinks=false,pdfborder={0 0 0}]{hyperref}
\usepackage{amsmath}
\usepackage{seqsplit}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\textbf{RWA Platform --- Audit Certifié}}
\fancyhead[R]{\textbf{""" + esc_asset_id + r"""}}
\fancyfoot[C]{Page \thepage\ / \pageref{LastPage} --- Généré par """ + esc_gen_by + r""" --- """ + esc_gen_date + r"""}

\begin{document}

\begin{center}
{\Huge \textbf{RAPPORT D'AUDIT CERTIFIÉ}}\\[0.5cm]
{\Large \textbf{""" + esc_asset_name + r""" (""" + esc_asset_id + r""")}}
\end{center}
\rule{\textwidth}{0.4pt}
\vspace{0.5cm}

\begin{table}[h]
\centering
\begin{tabular}{ll}
\toprule
\textbf{ISIN} & """ + esc_isin + r""" \\
\textbf{LEI Émetteur} & """ + esc_lei + r""" \\
\textbf{Valeur Nominale} & """ + esc_str_val + r""" EUR \\
\textbf{Statut Courant} & """ + status_color + r""" \\
\textbf{Date de Génération} & """ + esc_gen_date + r""" \\
\bottomrule
\end{tabular}
\end{table}

\vspace{0.5cm}
\noindent\textbf{Empreinte numérique SHA-256 du PDF :}\\
\texttt{\seqsplit{""" + esc_hash + r"""}}

\vspace{1cm}
\section*{1. Journal de Provenance Hyperledger Fabric}

\begin{longtable}{p{0.5cm}p{3cm}p{1.5cm}p{2cm}p{4cm}p{2cm}p{3cm}}
\toprule
\textbf{N°} & \textbf{Date/Heure} & \textbf{Action} & \textbf{Acteur MSP} & \textbf{Acteur DN} & \textbf{Montant} & \textbf{Justification} \\
\midrule
\endfirsthead
\multicolumn{7}{c}%
{{\bfseries \tablename\ \thetable{} --- suite de la page précédente}} \\
\toprule
\textbf{N°} & \textbf{Date/Heure} & \textbf{Action} & \textbf{Acteur MSP} & \textbf{Acteur DN} & \textbf{Montant} & \textbf{Justification} \\
\midrule
\endhead
\midrule
\multicolumn{7}{r}{{À suivre sur la page suivante}} \\
\endfoot
\bottomrule
\endlastfoot
""" + prov_table_body + r"""
\end{longtable}

\vspace{1cm}
\section*{2. Preuve d'Intégrité Cryptographique}

\begin{center}
{\Huge """ + st_global + r"""}
\end{center}
\vspace{0.5cm}

\begin{longtable}{llcc}
\toprule
\textbf{N°} & \textbf{TxID} & \textbf{Hash SHA-256} & \textbf{Statut} \\
\midrule
\endfirsthead
\multicolumn{4}{c}%
{{\bfseries \tablename\ \thetable{} --- suite de la page précédente}} \\
\toprule
\textbf{N°} & \textbf{TxID} & \textbf{Hash SHA-256} & \textbf{Statut} \\
\midrule
\endhead
\midrule
\multicolumn{4}{r}{{À suivre sur la page suivante}} \\
\endfoot
\bottomrule
\endlastfoot
""" + int_table_body + r"""
\end{longtable}
\begin{center}
Vérification réalisée le """ + esc_gen_date + r""" --- """ + str(int_total) + r""" enregistrement(s) contrôlé(s)
\end{center}

\vspace{1cm}
\section*{3. Informations Réglementaires}

\begin{table}[h]
\centering
\begin{tabularx}{\textwidth}{lX}
\toprule
\textbf{Réseau Fabric} & rwa-channel \\
\textbf{Organisations endorseuses} & BNPParibasMSP + AMFRegulateurMSP \\
\textbf{Politique d'endorsement} & MAJORITY \\
\textbf{Références réglementaires applicables} & MiCA art.68/70/76, AMLD6, EMIR \\
\bottomrule
\end{tabularx}
\end{table}

\label{LastPage}
\end{document}
"""
        return tex

    async def generate(self, asset_id: str, asset_state: dict, provenance: list[ProvenanceRecord], integrity: IntegrityReport, generated_by: str) -> bytes:
        tex_1 = self._build_tex(asset_id, asset_state, provenance, integrity, generated_by, "CALCUL EN COURS...")
        pdf_1 = await self._compile_latex(tex_1)

        doc_hash = hashlib.sha256(pdf_1).hexdigest()

        tex_2 = self._build_tex(asset_id, asset_state, provenance, integrity, generated_by, doc_hash)
        pdf_2 = await self._compile_latex(tex_2)
        return pdf_2
