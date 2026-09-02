import os

from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="ReqPilot SC - Мониторинг насосной станции",
        project_features=[
            "TABLE_SCREEN",
            "TRACEABILITY_SCREEN",
            "DEEP_TRACEABILITY_SCREEN",
            "SEARCH",
            "TRACEABILITY_MATRIX_SCREEN",
            "REQIF",
            "HTML2PDF",
        ],
        server_host="127.0.0.1",
        reqif_enable_mid=True,
        reqif_multiline_is_xhtml=True,
        favicon_path="assets/favicon.svg",
        custom_css_path="assets/custom.css",
        document_line_width=100,
        # Optional explicit driver keeps native PDF export reproducible in
        # restricted/offline environments.  When unset, html2pdf4doc uses its
        # own version-matched discovery and download flow.
        chromedriver=os.environ.get("REQPILOT_CHROMEDRIVER"),
    )
