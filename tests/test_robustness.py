from app.application.change_notifier import ChangeNotifier
from app.application.validation import parse_time
from app.container import Services
from app.web import create_app


class BrokenWeekView:
    """Simulates an infrastructure outage (e.g. the database is unreachable)."""

    def get_week(self, user_id, week_start):
        raise RuntimeError("database is down")

    def unread_notifications(self, user_id):
        return []


def logged_in_client(services):
    client = create_app(services=services).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    return client


def test_unexpected_failure_shows_a_friendly_lithuanian_page_instead_of_crashing():
    response = logged_in_client(Services(week_view=BrokenWeekView())).get("/week/")
    page = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "Įvyko klaida" in page and "Anksčiau patvirtinti duomenys nepakeisti" in page
    assert "Traceback" not in page


def test_normal_http_errors_are_not_swallowed():
    assert logged_in_client(Services()).get("/no-such-page").status_code == 404


def test_change_notifier_calls_every_subscriber():
    seen = []
    notifier = ChangeNotifier()
    notifier.subscribe(lambda user_id: seen.append(("a", user_id)))
    notifier.subscribe(lambda user_id: seen.append(("b", user_id)))
    notifier(7)
    assert seen == [("a", 7), ("b", 7)]


def test_time_parsing_accepts_only_24h_hh_mm():
    assert parse_time("09:05").minute == 5
    assert parse_time("24:00") is None and parse_time("9") is None and parse_time(None) is None
