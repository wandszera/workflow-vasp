function parseDOSCAR(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(l => l !== '');
  if (lines.length < 6) return null;
  
  try {
    const params = lines[5].split(/\s+/).map(Number);
    const numPoints = params[2];
    const fermi = params[3];
    
    const energies = [];
    const dosUp = [];
    const dosDown = [];
    const isSpin = lines[6].split(/\s+/).length >= 5;
    
    for (let i = 0; i < numPoints; i++) {
      const lineIdx = 6 + i;
      if (lineIdx >= lines.length) break;
      const cols = lines[lineIdx].split(/\s+/).map(Number);
      if (cols.length < 3) continue;
      
      // Shift energy relative to Fermi level
      energies.push(cols[0] - fermi);
      
      if (isSpin) {
        dosUp.push(cols[1]);
        dosDown.push(-cols[2]); // Plot spin-down as negative
      } else {
        dosUp.push(cols[1]);
      }
    }
    
    return {
      fermi: 0.0,
      originalFermi: fermi,
      isSpin: isSpin,
      energies: energies,
      dosUp: dosUp,
      dosDown: dosDown
    };
  } catch (e) {
    console.error("Erro ao analisar DOSCAR:", e);
    return null;
  }
}

function parseEIGENVAL(text, fermiEnergy = 0.0) {
  const lines = text.split('\n').map(l => l.trim()).filter(l => l !== '');
  if (lines.length < 6) return null;
  
  try {
    const params = lines[5].split(/\s+/).map(Number);
    const numKPoints = params[1];
    const numBands = params[2];
    
    const bands = Array.from({ length: numBands }, () => []);
    const kpointX = [];
    
    let lineIdx = 6;
    for (let k = 0; k < numKPoints; k++) {
      // Find kpoint coordinates line (usually contains 4 numbers)
      while (lineIdx < lines.length && lines[lineIdx].split(/\s+/).length < 4) {
        lineIdx++;
      }
      if (lineIdx >= lines.length) break;
      
      kpointX.push(k + 1);
      lineIdx++; // move to first band
      
      for (let b = 0; b < numBands; b++) {
        if (lineIdx >= lines.length) break;
        const cols = lines[lineIdx].split(/\s+/).map(Number);
        const energy = cols[1];
        // Shift energy relative to Fermi level
        bands[b].push(energy - fermiEnergy);
        lineIdx++;
      }
    }
    
    return {
      numKPoints: numKPoints,
      numBands: numBands,
      bands: bands,
      kpoints: kpointX
    };
  } catch (e) {
    console.error("Erro ao analisar EIGENVAL:", e);
    return null;
  }
}

function renderDOSChart(containerId, data) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  const width = container.clientWidth || 500;
  const height = 300;
  const padding = { top: 20, right: 30, bottom: 40, left: 50 };
  
  const minEnergy = Math.min(...data.energies);
  const maxEnergy = Math.max(...data.energies);
  
  // Find limits for DOS axes
  let maxDos = Math.max(...data.dosUp);
  let minDos = data.isSpin ? Math.min(...data.dosDown) : 0.0;
  const absoluteMaxDos = Math.max(maxDos, Math.abs(minDos));
  
  if (data.isSpin) {
    // Symmetrical scale for spin up/down
    maxDos = absoluteMaxDos;
    minDos = -absoluteMaxDos;
  }
  
  const scaleX = (val) => padding.left + ((val - minEnergy) / (maxEnergy - minEnergy)) * (width - padding.left - padding.right);
  const scaleY = (val) => height - padding.bottom - ((val - minDos) / (maxDos - minDos)) * (height - padding.top - padding.bottom);
  
  // Build SVG Paths
  let pathUp = `M ${scaleX(data.energies[0])} ${scaleY(data.dosUp[0])}`;
  for (let i = 1; i < data.energies.length; i++) {
    pathUp += ` L ${scaleX(data.energies[i])} ${scaleY(data.dosUp[i])}`;
  }
  
  let pathDown = "";
  if (data.isSpin) {
    pathDown = `M ${scaleX(data.energies[0])} ${scaleY(data.dosDown[0])}`;
    for (let i = 1; i < data.energies.length; i++) {
      pathDown += ` L ${scaleX(data.energies[i])} ${scaleY(data.dosDown[i])}`;
    }
  }
  
  const zeroX = scaleX(0.0); // Fermi Energy shifted to 0.0
  const zeroY = scaleY(0.0); // Zero DOS line
  
  const svg = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background: transparent; font-family: 'Outfit', sans-serif;">
      <!-- Grid Lines -->
      <line x1="${padding.left}" y1="${zeroY}" x2="${width - padding.right}" y2="${zeroY}" stroke="rgba(255,255,255,0.08)" stroke-width="1" />
      <line x1="${zeroX}" y1="${padding.top}" x2="${zeroX}" y2="${height - padding.bottom}" stroke="#f43f5e" stroke-width="1.5" stroke-dasharray="4,4" />
      <text x="${zeroX + 5}" y="${padding.top + 15}" fill="#f43f5e" font-size="0.75rem">Nivel de Fermi (E_f)</text>
      
      <!-- DOS Up Path -->
      <path d="${pathUp}" fill="none" stroke="#6366f1" stroke-width="2" />
      ${data.isSpin ? `<path d="${pathDown}" fill="none" stroke="#10b981" stroke-width="2" />` : ''}
      
      <!-- Axes -->
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      
      <!-- X-axis Labels -->
      <text x="${width / 2}" y="${height - 5}" fill="var(--text-muted)" font-size="0.8rem" text-anchor="middle">Energia - E_f (eV)</text>
      <text x="${padding.left}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${minEnergy.toFixed(1)}</text>
      <text x="${width - padding.right}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="middle">${maxEnergy.toFixed(1)}</text>
      <text x="${zeroX}" y="${height - padding.bottom + 15}" fill="#fff" font-size="0.7rem" text-anchor="middle">0.0</text>
      
      <!-- Y-axis Labels -->
      <text x="${padding.left - 10}" y="${padding.top + 5}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${maxDos.toFixed(1)}</text>
      <text x="${padding.left - 10}" y="${height - padding.bottom}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${data.isSpin ? minDos.toFixed(1) : '0.0'}</text>
      
      <!-- Legend -->
      <g transform="translate(${width - 120}, ${padding.top})">
        <rect x="0" y="0" width="10" height="10" fill="#6366f1" />
        <text x="15" y="9" fill="#fff" font-size="0.75rem">${data.isSpin ? 'Spin Up' : 'DOS Total'}</text>
        ${data.isSpin ? `
          <rect x="0" y="15" width="10" height="10" fill="#10b981" />
          <text x="15" y="24" fill="#fff" font-size="0.75rem">Spin Down</text>
        ` : ''}
      </g>
    </svg>
  `;
  
  container.innerHTML = svg;
}

function renderBandsChart(containerId, data) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  const width = container.clientWidth || 500;
  const height = 300;
  const padding = { top: 20, right: 30, bottom: 40, left: 50 };
  
  // Find energy limits across all bands
  let minEnergy = floatMax = -9999.0;
  let maxEnergy = floatMin = 9999.0;
  
  data.bands.forEach(band => {
    band.forEach(e => {
      if (e < minEnergy) minEnergy = e;
      if (e > maxEnergy) maxEnergy = e;
    });
  });
  
  // Clamp range to +/- 10 eV around Fermi for optimal visualization of electronic bands
  const limitMin = Math.max(minEnergy, -8.0);
  const limitMax = Math.min(maxEnergy, 8.0);
  
  const numKPoints = data.numKPoints;
  
  const scaleX = (kIdx) => padding.left + ((kIdx - 1) / (numKPoints - 1)) * (width - padding.left - padding.right);
  const scaleY = (val) => height - padding.bottom - ((val - limitMin) / (limitMax - limitMin)) * (height - padding.top - padding.bottom);
  
  let bandsPathsHtml = "";
  
  data.bands.forEach((band, idx) => {
    let path = `M ${scaleX(1)} ${scaleY(band[0])}`;
    for (let i = 1; i < band.length; i++) {
      const y = scaleY(band[i]);
      // Skip drawing lines outside our clamped viewport to keep SVG clean
      path += ` L ${scaleX(i + 1)} ${y}`;
    }
    // Color alternate conduction (above 0 eV) vs valence (below 0 eV) bands
    const isValence = band[0] < 0.0;
    const strokeColor = isValence ? "#6366f1" : "#10b981";
    bandsPathsHtml += `<path d="${path}" fill="none" stroke="${strokeColor}" stroke-width="1.2" opacity="0.8" />`;
  });
  
  const zeroX = scaleX(1);
  const zeroY = scaleY(0.0); // Fermi Energy
  
  const svg = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background: transparent; font-family: 'Outfit', sans-serif;">
      <!-- Grid / Fermi Line -->
      <line x1="${padding.left}" y1="${zeroY}" x2="${width - padding.right}" y2="${zeroY}" stroke="#f43f5e" stroke-width="1.5" stroke-dasharray="4,4" />
      <text x="${padding.left + 10}" y="${zeroY - 5}" fill="#f43f5e" font-size="0.75rem">Nivel de Fermi (E_f = 0)</text>
      
      <!-- Band Dispersion Paths -->
      <g clip-path="url(#chart-area)">
        <clipPath id="chart-area">
          <rect x="${padding.left}" y="${padding.top}" width="${width - padding.left - padding.right}" height="${height - padding.top - padding.bottom}" />
        </clipPath>
        ${bandsPathsHtml}
      </g>
      
      <!-- Axes -->
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${width - padding.right}" y1="${padding.top}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      
      <!-- X-axis Labels -->
      <text x="${width / 2}" y="${height - 5}" fill="var(--text-muted)" font-size="0.8rem" text-anchor="middle">Pontos K (Zona de Brillouin)</text>
      <text x="${padding.left}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.75rem" text-anchor="middle">Gamma</text>
      <text x="${width - padding.right}" y="${height - padding.bottom + 15}" fill="var(--text-muted)" font-size="0.75rem" text-anchor="middle">X / M / K</text>
      
      <!-- Y-axis Labels -->
      <text x="${padding.left - 10}" y="${padding.top + 5}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${limitMax.toFixed(1)} eV</text>
      <text x="${padding.left - 10}" y="${height - padding.bottom}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${limitMin.toFixed(1)} eV</text>
    </svg>
  `;
  
  container.innerHTML = svg;
}
