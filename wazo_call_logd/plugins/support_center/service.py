# Copyright 2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

from .exceptions import QueueNotFoundException, RangeTooLargeException


class QueueStatisticsService(object):
    def __init__(self, dao):
        self._dao = dao

    def _generate_subinterval(self, from_, until, time_delta):
        current = from_
        next_datetime = current + time_delta
        while current < until:
            yield current, next_datetime
            current = next_datetime
            next_datetime = current + time_delta
            if next_datetime > until:
                next_datetime = until

    def _generate_interval(self, interval, from_, until):
        time_deltas = {
            'hour': relativedelta(hours=1),
            'day': relativedelta(days=1),
            'month': relativedelta(months=1),
        }

        time_delta = time_deltas.get(interval, 'hour')

        if time_delta == time_deltas['hour']:
            if from_ + relativedelta(months=1) < until:
                raise RangeTooLargeException(
                    details='Maximum of 1 month for interval by hour'
                )
        if interval:
            yield from self._generate_subinterval(from_, until, time_delta)
        else:
            yield from_, until

    def _get_tomorrow(self):
        today = datetime.now(tz=timezone.utc)
        return datetime(
            today.year, today.month, today.day, tzinfo=timezone.utc
        ) + relativedelta(days=1)

    def _datetime_in_week_days(self, date_time, week_days):
        return date_time.isoweekday() in week_days

    def _datetime_in_time_interval(self, date_time, start_time, end_time):
        return start_time <= date_time.hour <= end_time

    def get(
        self,
        tenant_uuids,
        queue_id,
        from_=None,
        until=None,
        interval=None,
        start_time=None,
        end_time=None,
        week_days=None,
        **kwargs
    ):
        queue_stats = list()

        from_ = from_ or self._dao.find_oldest_time(queue_id)
        until = until or self._get_tomorrow()

        if interval:
            for start, end in self._generate_interval(interval, from_, until):
                if start_time and not self._datetime_in_time_interval(
                    start, start_time, end_time
                ):
                    continue
                if end_time and not self._datetime_in_time_interval(
                    end, start_time, end_time
                ):
                    continue
                if week_days and not self._datetime_in_week_days(start, week_days):
                    continue

                interval_timeframe = {
                    'from': start,
                    'until': end,
                    'queue_id': queue_id,
                }
                interval_stats = (
                    self._dao.get_interval_by_queue(
                        tenant_uuids,
                        queue_id=queue_id,
                        from_=start,
                        until=end,
                        start_time=start_time,
                        end_time=end_time,
                        week_days=week_days,
                        **kwargs
                    )
                    or {}
                )
                interval_stats.update(interval_timeframe)
                queue_stats.append(interval_stats)

        period_timeframe = {
            'from': from_,
            'until': until,
            'queue_id': queue_id,
        }
        period_stats = (
            self._dao.get_interval_by_queue(
                tenant_uuids,
                queue_id=queue_id,
                from_=from_,
                until=until,
                start_time=start_time,
                end_time=end_time,
                week_days=week_days,
                **kwargs
            )
            or {}
        )
        period_stats.update(period_timeframe)

        queue_stats.append(period_stats)

        if not queue_stats:
            raise QueueNotFoundException(details={'queue_id': queue_id})

        return {
            'items': queue_stats,
            'total': len(queue_stats),
        }

    def list(self, tenant_uuids, from_=None, until=None, **kwargs):

        queue_stats = self._dao.get_interval(
            tenant_uuids, from_=from_, until=until, **kwargs
        )
        until = until or self._get_tomorrow()

        queue_stats_items = []
        for queue_stat in queue_stats:
            queue_stats_item = {**queue_stat}

            from_date = from_ or None
            if queue_stat.get('queue_id') and not from_date:
                from_date = self._dao.find_oldest_time(queue_stat['queue_id'])

            queue_stats_item.update(
                {
                    'from': from_date,
                    'until': until,
                }
            )
            queue_stats_items.append(queue_stats_item)

        return {
            'items': queue_stats_items,
            'total': len(queue_stats),
        }