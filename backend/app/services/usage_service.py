"""AI usage for the Usage page: this month's requests by feature and model, a daily series,
and today's remaining free requests (the free-tier quota belongs to the app's key)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import UsageEvent, User
from app.schemas.usage import DayUsage, FeatureUsage, ModelUsage, UsageOut
from app.services import llm_gateway

DAYS = 30


async def usage(db: AsyncSession, user: User) -> UsageOut:
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    mine = (UsageEvent.user_id == user.id, UsageEvent.created_at >= month_start)

    by_feature = (
        await db.execute(
            select(
                UsageEvent.feature,
                func.count(),
                func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                func.coalesce(func.sum(UsageEvent.output_tokens), 0),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0),
            )
            .where(*mine)
            .group_by(UsageEvent.feature)
        )
    ).all()
    by_model = (
        await db.execute(
            select(UsageEvent.provider, UsageEvent.model, func.count())
            .where(*mine)
            .group_by(UsageEvent.provider, UsageEvent.model)
            .order_by(func.count().desc())
        )
    ).all()

    since = (now - timedelta(days=DAYS - 1)).date()
    day = cast(UsageEvent.created_at, Date)
    per_day = dict(
        (
            await db.execute(
                select(day, func.count())
                .where(
                    UsageEvent.user_id == user.id,
                    UsageEvent.created_at >= datetime.combine(since, datetime.min.time(), UTC),
                )
                .group_by(day)
            )
        ).all()
    )
    daily = [
        DayUsage(day=d, requests=int(per_day.get(d, 0)))
        for d in (since + timedelta(days=i) for i in range(DAYS))
    ]

    settings = get_settings()
    features = [
        FeatureUsage(
            feature=f,
            requests=int(n),
            input_tokens=int(i),
            output_tokens=int(o),
            cost_usd=float(c),
        )
        for f, n, i, o, c in sorted(by_feature, key=lambda r: -r[1])
    ]
    return UsageOut(
        month_start=month_start.date(),
        requests=sum(f.requests for f in features),
        input_tokens=sum(f.input_tokens for f in features),
        output_tokens=sum(f.output_tokens for f in features),
        cost_usd=round(sum(f.cost_usd for f in features), 4),
        by_feature=features,
        by_model=[ModelUsage(provider=p, model=m, requests=int(n)) for p, m, n in by_model],
        daily=daily,
        requests_left_today=llm_gateway.requests_left_today(),
        daily_request_limit=settings.llm_rpd or None,
        provider=settings.llm_provider,
        writing_provider=settings.writing_llm_provider or settings.llm_provider,
    )
