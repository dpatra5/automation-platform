from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./rewind.db"
    base_url: str = "http://localhost:8000"
    # Used for the deep links Rewind writes into Jira comments.
    dashboard_url: str = "http://localhost:5173"
    artifacts_dir: str = "artifacts"
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    log_level: str = "INFO"

    # Regression runs open a real, visible Chrome window by default so the
    # traversal can be watched. Set HEADLESS=true for CI / headless servers.
    headless: bool = False
    # "chrome" uses the locally installed Google Chrome; empty falls back to
    # Playwright's bundled Chromium (which is also the automatic fallback).
    browser_channel: str = "chrome"
    # A managed Chrome carrying the BlockThirdPartyCookies policy drops the
    # cross-site cookies an SSO session is made of, and no switch inside the
    # browser can override a policy. Runs therefore move to bundled Chromium,
    # which the policy does not cover. Set false to drive managed Chrome anyway.
    require_third_party_cookies: bool = True
    slow_mo_ms: int = 250
    step_timeout_ms: int = 15000
    # How long to keep looking for an element that cannot be found at all.
    # Short on purpose: a step that has lost its element is not going to find
    # it, and waiting only delays the report. Spent before the action starts,
    # so the step timeout above still measures the action itself.
    element_ready_timeout_ms: int = 30000
    # How long to wait once the element has been found on screen but the app
    # is holding it switched off - a composer locked while an answer streams
    # in, a save button disabled until the upload finishes. That is the app
    # working, not a broken step, and a tester would simply wait, so this is
    # allowed to run into minutes. Only ever spent when a locked element has
    # actually been seen, and only on a step's first attempt.
    element_busy_timeout_ms: int = 180000
    # Extra attempts for a step whose element never became actionable. The
    # browser refuses such an action rather than half-performing it, so trying
    # again is safe, and the app is given a moment to go quiet in between.
    # Retries are for a page that was mid-change, so they get the short budget:
    # waiting out a busy app happens once, on the first attempt.
    step_retry_attempts: int = 2
    # Navigation needs its own, larger budget: DNS, TLS and a cold redirect can
    # eat far more than a click on an element that is already on screen.
    navigation_timeout_ms: int = 45000
    viewport_width: int = 1440
    viewport_height: int = 900
    # Every run is filmed. Headed Chrome only paints its recording surface while
    # its window is in front, so the runner raises the window before it starts.
    # If a file still ends up unusable the dashboard falls back to a filmstrip
    # built from the per-step screenshots. Set VIDEO=off to skip filming.
    video: str = "on"

    jira_url: str = ""
    jira_token: str = ""
    # Jira Cloud authenticates with the account email plus an API token (basic
    # auth); Data Center and Server take a Personal Access Token as a bearer
    # token and answer basic auth with a 500. "auto" picks by host and retries
    # with the other scheme if the first one is refused. Force it with
    # JIRA_AUTH=bearer or JIRA_AUTH=basic.
    jira_auth: str = "auto"
    jira_email: str = ""
    jira_verify_ssl: bool = True
    jira_timeout_seconds: int = 20
    # The issue type a project's Jira key has to have to be accepted.
    jira_test_execution_type: str = "Test Execution"
    # Evidence files are attached to the issue alongside the comment.
    jira_attach_evidence: bool = True
    jira_max_attachment_mb: int = 10

    confluence_url: str = ""
    confluence_token: str = ""
    bitbucket_url: str = ""
    bitbucket_token: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
