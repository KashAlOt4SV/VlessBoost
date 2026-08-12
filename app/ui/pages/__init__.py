"""Page builders live on BoosterApp for now; this package marks the page layer."""

# Intentionally empty — layouts are methods on app.ui.app.BoosterApp
# (_build_home_page, _build_boost_page, …) to keep handlers and widgets coupled
# without duplicating state. Split further only if files grow past maintainability.
