const { test } = require('node:test');
const assert = require('node:assert/strict');
const { calendarDay, pointDay, axisDay, dailyObservations, chartTicks, chartValue, dateLayout, clampWindow, zoomWindow, resizeWindow, observationSegments } = require('../../.runtime/portfolio-chart-test/chartLayout.js');
const p = (at, changes = {}) => ({ observed_at: at, event_type: 'valuation', record_id: 1, interval: 1, total_assets: '120000',
  cumulative_profit: '25000', cumulative_profit_rate: '0.25', cumulative_return: '-0.0218', profit: '-2103.07', asset_returns: {}, ...changes });

test('four curve metrics select the corresponding amount or rate, preserving zero and unknown', () => {
  const point = p('2026-08-24T08:00:00Z');
  assert.equal(chartValue(point, 'total_return'), 25);
  assert.equal(chartValue(point, 'total_profit'), 25000);
  assert.equal(chartValue(point, 'return'), -2.18);
  assert.equal(chartValue(point, 'profit'), -2103.07);
  assert.equal(chartValue({ ...point, cumulative_profit_rate: null }, 'total_return'), null);
  assert.equal(chartValue({ ...point, cumulative_profit: '0' }, 'total_profit'), 0);
});

test('dates use the valuation day first, otherwise Beijing day, with no time or locale separators', () => {
  const point = p('2026-08-24T18:00:00Z');
  assert.equal(calendarDay(point.observed_at), '2026-08-25');
  assert.equal(pointDay({ ...point, valuation_date: '2026-08-24' }), '2026-08-24');
  assert.equal(axisDay('2026-08-24'), '2026-08-24');
  assert.equal(axisDay('2026-10-17', '2026-08-24'), '10-17');
  assert.equal(axisDay('2027-01-05', '2026-12-31'), '2027-01-05');
});

test('one daily point uses last valid valuation, retaining all intraday records and entirely missing days', () => {
  const first = p('2026-10-17T08:00:00Z', { record_id: 1 });
  const last = p('2026-10-17T09:00:00Z', { record_id: 2, cumulative_profit: '26000' });
  const invalid = p('2026-10-17T10:00:00Z', { record_id: 3, total_assets: null });
  const missingDay = p('2026-10-18T08:00:00Z', { record_id: 4, total_assets: null });
  const daily = dailyObservations([invalid, first, last, missingDay]);
  assert.equal(daily.length, 2);
  assert.equal(daily[0].point, last);
  assert.deepEqual(daily[0].records, [first, last, invalid]);
  assert.equal(daily[1].point, missingDay);
  // A valid asset total with an inapplicable rate must not fall back to an earlier positive rate.
  const withdrawn = { ...last, cumulative_profit_rate: null };
  assert.equal(dailyObservations([first, withdrawn])[0].point, withdrawn);
});

test('positive, negative, mixed, flat and small percentage axes always include a real zero tick', () => {
  for (const values of [[114, -2103], [2, 3], [-100, -90], [0], [null], [0.002, -0.001]]) {
    const scale = chartTicks(values, true);
    assert(scale.ticks.includes(0));
    assert(scale.max > scale.min);
    for (const value of values.filter(v => v != null)) assert(value >= scale.min && value <= scale.max);
    assert.equal(scale.label(0), '0%');
  }
  assert.equal(chartTicks([-5020.13, 1100], false).label(1000), '1,000');
});

test('dense dates fit the full interval in one window, retaining points while sampling axis labels', () => {
  const days = ['2026-08-24', '2026-09-01', '2026-10-16', '2026-10-17'];
  const layout = dateLayout(days, 420);
  assert.deepEqual(layout.days, days);
  assert.equal(layout.width, 420);
  assert.equal(layout.x(days[0]), 110);
  assert.equal(layout.x(days[3]), 366);
  assert.equal(layout.ticks[0].day, days[0]);
  assert.equal(layout.ticks[layout.ticks.length - 1].day, days[3]);
  const single = dateLayout([days[0]], 420);
  assert(Number.isFinite(single.x(days[0])));
});

test('zoom uses an anchor, pan preserves span at boundaries, and range handles cannot cross', () => {
  const zoomed = zoomWindow({start:0,end:1},0.5,0.25);
  assert.deepEqual(zoomed, {start:0.125,end:0.625});
  assert.deepEqual(clampWindow(-0.5,0), {start:0,end:0.5});
  assert.deepEqual(clampWindow(0.75,1.25), {start:0.5,end:1});
  assert.deepEqual(zoomWindow(zoomed,100), {start:0,end:1});
  assert.deepEqual(resizeWindow({start:0.2,end:0.8},'start',0.9,0.1), {start:0.7000000000000001,end:0.8});
  assert.deepEqual(resizeWindow({start:0.2,end:0.8},'end',0,0.1), {start:0.2,end:0.30000000000000004});
  const days=['2026-08-24','2026-09-01','2026-10-17'];
  const layout=dateLayout(days,900, {start:0.5,end:1});
  assert(layout.x(days[0])<110);
  assert.equal(layout.x(days[2]),846);
});

test('missing values use a separate bridge without zero points; period resets stay disconnected', () => {
  const points=[p('2026-01-01'),p('2026-01-02'),p('2026-01-03')];
  assert.deepEqual(observationSegments(points,[1,null,3],true),[{from:0,to:2,missing:true}]);
  assert.deepEqual(observationSegments(points,[1,2,3],true),[{from:0,to:1,missing:false},{from:1,to:2,missing:false}]);
  const changed=[points[0],{...points[1],interval:2}, {...points[2],interval:2}];
  assert.deepEqual(observationSegments(changed,[1,null,3],false),[]);
  assert.deepEqual(observationSegments(changed,[1,null,3],true),[{from:0,to:2,missing:true}]);
  assert.deepEqual(observationSegments(points,[null,null,3],true),[]);
});
