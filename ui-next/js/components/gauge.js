// gauge.js — Semi-circle gauge chart (speedometer style)
// Returns an SVG string. No dependencies.

/**
 * Render a semi-circle gauge chart.
 *
 * @param {object} opts
 * @param {number} opts.value - Current value
 * @param {number} opts.max   - Maximum value (full scale)
 * @param {string} [opts.label] - Text label below the value
 * @param {Array<{ from: number, to: number, color: string }>} [opts.zones] - Background arc zones
 * @returns {string} SVG markup string
 */
export function gaugeChart({ value, max, label, zones }) {
  const w = 200;
  const h = 120;
  const cx = w / 2;
  const cy = 105; // center of the arc circle (near the bottom)
  const r = 80;   // radius

  // Arc spans from PI (180 deg, left) to 0 (0 deg, right)
  // Angle 0 = full max, angle PI = 0 value
  const startAngle = Math.PI;  // left side (value = 0)
  const endAngle = 0;          // right side (value = max)

  /**
   * Convert a value to an angle on the semicircle arc.
   * @param {number} v
   * @returns {number} angle in radians
   */
  function valueToAngle(v) {
    const clamped = Math.max(0, Math.min(v, max));
    const ratio = clamped / (max || 1);
    return startAngle - ratio * (startAngle - endAngle);
  }

  /**
   * Convert an angle to SVG coordinates.
   * @param {number} angle
   * @param {number} radius
   * @returns {{ x: number, y: number }}
   */
  function polarToCart(angle, radius) {
    return {
      x: cx + radius * Math.cos(angle),
      y: cy - radius * Math.sin(angle),
    };
  }

  /**
   * Create an SVG arc path from one angle to another.
   * @param {number} a1 - Start angle (radians)
   * @param {number} a2 - End angle (radians)
   * @param {number} radius
   * @returns {string}
   */
  function arcPath(a1, a2, radius) {
    const start = polarToCart(a1, radius);
    const end = polarToCart(a2, radius);
    const sweep = a1 > a2 ? 1 : 0;
    const largeArc = Math.abs(a1 - a2) > Math.PI ? 1 : 0;
    return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 ${largeArc} ${sweep} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
  }

  // Build zone arcs (background segments)
  const zoneArcs = (zones || [])
    .map((zone) => {
      const a1 = valueToAngle(zone.from);
      const a2 = valueToAngle(zone.to);
      return `<path d="${arcPath(a1, a2, r)}" fill="none" stroke="${zone.color}" stroke-width="12" stroke-linecap="butt" opacity="0.35" />`;
    })
    .join('');

  // Track arc (thin gray background)
  const trackArc = `<path d="${arcPath(startAngle, endAngle, r)}" fill="none" stroke="currentColor" stroke-width="4" opacity="0.15" />`;

  // Needle
  const needleAngle = valueToAngle(value);
  const needleTip = polarToCart(needleAngle, r - 10);
  const needleBase1 = polarToCart(needleAngle + Math.PI / 2, 4);
  const needleBase2 = polarToCart(needleAngle - Math.PI / 2, 4);

  const needle = `
    <polygon
      points="${needleBase1.x.toFixed(2)},${needleBase1.y.toFixed(2)} ${needleTip.x.toFixed(2)},${needleTip.y.toFixed(2)} ${needleBase2.x.toFixed(2)},${needleBase2.y.toFixed(2)}"
      fill="currentColor"
    />
    <circle cx="${cx}" cy="${cy}" r="5" fill="currentColor" />`;

  // Value text
  const valueText = `<text x="${cx}" y="${cy - 20}" text-anchor="middle" class="font-heading" style="font-size: 22px; font-weight: 700;" fill="currentColor">${value}</text>`;

  // Label text
  const labelText = label
    ? `<text x="${cx}" y="${cy - 4}" text-anchor="middle" style="font-size: 10px; font-weight: 500;" fill="currentColor" opacity="0.5">${label}</text>`
    : '';

  // Min / Max labels at the arc endpoints
  const minLabel = `<text x="${(cx - r + 2).toFixed(0)}" y="${cy + 14}" text-anchor="start" style="font-size: 9px; font-weight: 500;" fill="currentColor" opacity="0.35">0</text>`;
  const maxLabel = `<text x="${(cx + r - 2).toFixed(0)}" y="${cy + 14}" text-anchor="end" style="font-size: 9px; font-weight: 500;" fill="currentColor" opacity="0.35">${max}</text>`;

  return `
    <svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" class="text-fg">
      ${trackArc}
      ${zoneArcs}
      ${needle}
      ${valueText}
      ${labelText}
      ${minLabel}
      ${maxLabel}
    </svg>`;
}
