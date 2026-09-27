function renderPhononCharts(feContainerId, cvContainerId, data) {
  const feContainer = document.getElementById(feContainerId);
  const cvContainer = document.getElementById(cvContainerId);

  if (!feContainer || !cvContainer) return;

  const temps = data.temperatures;
  const fe = data.free_energy;
  const entropy = data.entropy;
  const cv = data.heat_capacity;

  const width = feContainer.clientWidth || 500;
  const height = 300;
  const padding = { top: 25, right: 55, bottom: 45, left: 60 };

  // --- CHART 1: Free Energy & Entropy ---
  const minTemp = temps[0];
  const maxTemp = temps[temps.length - 1];

  const minFe = Math.min(...fe);
  const maxFe = Math.max(...fe);
  const feRange = maxFe - minFe || 1.0;

  const minS = Math.min(...entropy);
  const maxS = Math.max(...entropy);
  const sRange = maxS - minS || 1.0;

  const scaleTemp = (t) => padding.left + ((t - minTemp) / (maxTemp - minTemp)) * (width - padding.left - padding.right);
  const scaleFe = (val) => height - padding.bottom - ((val - minFe) / feRange) * (height - padding.top - padding.bottom);
  const scaleS = (val) => height - padding.bottom - ((val - minS) / sRange) * (height - padding.top - padding.bottom);

  let pathFe = `M ${scaleTemp(temps[0])} ${scaleFe(fe[0])}`;
  let pathS = `M ${scaleTemp(temps[0])} ${scaleS(entropy[0])}`;

  for (let i = 1; i < temps.length; i++) {
    pathFe += ` L ${scaleTemp(temps[i])} ${scaleFe(fe[i])}`;
    pathS += ` L ${scaleTemp(temps[i])} ${scaleS(entropy[i])}`;
  }

  const svgFe = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background: transparent; font-family: 'Outfit', sans-serif;">
      <!-- Grid -->
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${width - padding.right}" y1="${padding.top}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />

      <!-- Paths -->
      <path d="${pathFe}" fill="none" stroke="#6366f1" stroke-width="2.5" />
      <path d="${pathS}" fill="none" stroke="#f43f5e" stroke-width="2.5" />

      <!-- X Labels -->
      <text x="${width / 2}" y="${height - 5}" fill="var(--text-muted)" font-size="0.8rem" text-anchor="middle">Temperatura (K)</text>
      <text x="${padding.left}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${minTemp.toFixed(0)}</text>
      <text x="${width - padding.right}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${maxTemp.toFixed(0)}</text>

      <!-- Left Y (Free Energy) -->
      <text x="${padding.left - 10}" y="${padding.top + 5}" fill="#6366f1" font-size="0.7rem" text-anchor="end">${maxFe.toFixed(1)} F</text>
      <text x="${padding.left - 10}" y="${height - padding.bottom}" fill="#6366f1" font-size="0.7rem" text-anchor="end">${minFe.toFixed(1)} F</text>

      <!-- Right Y (Entropy) -->
      <text x="${width - padding.right + 10}" y="${padding.top + 5}" fill="#f43f5e" font-size="0.7rem" text-anchor="start">${maxS.toFixed(1)} S</text>
      <text x="${width - padding.right + 10}" y="${height - padding.bottom}" fill="#f43f5e" font-size="0.7rem" text-anchor="start">${minS.toFixed(1)} S</text>

      <!-- Legend -->
      <g transform="translate(${width / 2 - 80}, ${padding.top})">
        <rect x="0" y="0" width="10" height="10" fill="#6366f1" />
        <text x="15" y="9" fill="#fff" font-size="0.75rem">F (Energia Livre)</text>
        <rect x="130" y="0" width="10" height="10" fill="#f43f5e" />
        <text x="145" y="9" fill="#fff" font-size="0.75rem">S (Entropia)</text>
      </g>
    </svg>
  `;
  feContainer.innerHTML = svgFe;

  // --- CHART 2: Heat Capacity (Cv) ---
  const minCv = Math.min(...cv);
  const maxCv = Math.max(...cv);
  const cvRange = maxCv - minCv || 1.0;

  const scaleCv = (val) => height - padding.bottom - ((val - minCv) / cvRange) * (height - padding.top - padding.bottom);

  let pathCv = `M ${scaleTemp(temps[0])} ${scaleCv(cv[0])}`;
  for (let i = 1; i < temps.length; i++) {
    pathCv += ` L ${scaleTemp(temps[i])} ${scaleCv(cv[i])}`;
  }

  const svgCv = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background: transparent; font-family: 'Outfit', sans-serif;">
      <!-- Grid -->
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />

      <!-- Path -->
      <path d="${pathCv}" fill="none" stroke="#10b981" stroke-width="2.5" />

      <!-- X Labels -->
      <text x="${width / 2}" y="${height - 5}" fill="var(--text-muted)" font-size="0.8rem" text-anchor="middle">Temperatura (K)</text>
      <text x="${padding.left}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${minTemp.toFixed(0)}</text>
      <text x="${width - padding.right}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${maxTemp.toFixed(0)}</text>

      <!-- Y Labels -->
      <text x="${padding.left - 10}" y="${padding.top + 5}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${maxCv.toFixed(1)}</text>
      <text x="${padding.left - 10}" y="${height - padding.bottom}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${minCv.toFixed(1)}</text>

      <!-- Legend -->
      <g transform="translate(${width / 2 - 50}, ${padding.top})">
        <rect x="0" y="0" width="10" height="10" fill="#10b981" />
        <text x="15" y="9" fill="#fff" font-size="0.75rem">Cv (Capacidade Termica)</text>
      </g>
    </svg>
  `;
  cvContainer.innerHTML = svgCv;
}
