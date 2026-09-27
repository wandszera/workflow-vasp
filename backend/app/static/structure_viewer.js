function convertPoscarToXyzSupercell(poscarText, na = 1, nb = 1, nc = 1) {
  const lines = poscarText.split('\n').map(l => l.trim()).filter(l => l !== '');
  if (lines.length < 8) return null;
  
  try {
    const scale = parseFloat(lines[1]);
    const l1 = lines[2].split(/\s+/).map(Number);
    const l2 = lines[3].split(/\s+/).map(Number);
    const l3 = lines[4].split(/\s+/).map(Number);
    
    const m = [
      [l1[0] * scale, l1[1] * scale, l1[2] * scale],
      [l2[0] * scale, l2[1] * scale, l2[2] * scale],
      [l3[0] * scale, l3[1] * scale, l3[2] * scale]
    ];
    
    const parts5 = lines[5].split(/\s+/);
    const parts6 = lines[6].split(/\s+/);
    
    let elements = [];
    let counts = [];
    let lineOffset = 7;
    
    if (parts5.every(p => !isNaN(parseInt(p)))) {
      counts = parts5.map(Number);
      elements = counts.map((_, idx) => `X${idx + 1}`);
    } else {
      elements = parts5;
      counts = parts6.map(Number);
    }
    
    if (lines[lineOffset].toLowerCase().startsWith('s')) {
      lineOffset++;
    }
    
    const coordType = lines[lineOffset].toLowerCase();
    const isDirect = coordType.startsWith('d') || coordType.startsWith('f');
    lineOffset++;
    
    const atomElements = [];
    for (let i = 0; i < elements.length; i++) {
      for (let c = 0; c < counts[i]; c++) {
        atomElements.push(elements[i]);
      }
    }
    
    const totalAtoms = atomElements.length;
    const replicatedAtoms = totalAtoms * na * nb * nc;
    let xyzContent = `${replicatedAtoms}\nSupercell ${na}x${nb}x${nc} generated from POSCAR\n`;
    
    for (let da = 0; da < na; da++) {
      for (let db = 0; db < nb; db++) {
        for (let dc = 0; dc < nc; dc++) {
          for (let i = 0; i < totalAtoms; i++) {
            const rawCoord = lines[lineOffset + i].split(/\s+/).map(Number);
            let x, y, z;
            if (isDirect) {
              const fa = rawCoord[0] + da;
              const fb = rawCoord[1] + db;
              const fc = rawCoord[2] + dc;
              x = fa * m[0][0] + fb * m[1][0] + fc * m[2][0];
              y = fa * m[0][1] + fb * m[1][1] + fc * m[2][1];
              z = fa * m[0][2] + fb * m[1][2] + fc * m[2][2];
            } else {
              x = rawCoord[0] * scale + da * m[0][0] + db * m[1][0] + dc * m[2][0];
              y = rawCoord[1] * scale + da * m[0][1] + db * m[1][1] + dc * m[2][1];
              z = rawCoord[2] * scale + da * m[0][2] + db * m[1][2] + dc * m[2][2];
            }
            xyzContent += `${atomElements[i]} ${x.toFixed(6)} ${y.toFixed(6)} ${z.toFixed(6)}\n`;
          }
        }
      }
    }
    return { xyz: xyzContent, lattice: m };
  } catch (e) {
    console.error("Erro ao converter POSCAR para XYZ:", e);
    return null;
  }
}

function init3DmolViewer(canvasId, poscarText, na = 1, nb = 1, nc = 1, collidingIndices = [], styleName = "ball-and-stick") {
  const element = document.getElementById(canvasId);
  if (!element) return;
  
  const structData = convertPoscarToXyzSupercell(poscarText, na, nb, nc);
  if (!structData) {
    element.innerHTML = "<div style='color: #ef4444; padding: 1rem;'>Falha ao processar arquivo de estrutura.</div>";
    return;
  }
  
  element.innerHTML = "";
  
  const viewer = $3Dmol.createViewer($(element), {
    backgroundColor: '#0f172a'
  });
  
  viewer.addModel(structData.xyz, "xyz");
  
  if (styleName === "spacefill") {
    viewer.setStyle({}, { sphere: { scale: 0.75, colorscheme: 'Jmol' } });
  } else if (styleName === "wireframe") {
    viewer.setStyle({}, { line: { radius: 0.05, colorscheme: 'Jmol' } });
  } else {
    viewer.setStyle({}, { 
      sphere: { scale: 0.35, colorscheme: 'Jmol' },
      stick: { radius: 0.1, colorscheme: 'Jmol' } 
    });
  }

  // Highlight colliding atoms in red
  collidingIndices.forEach(idx => {
    viewer.setStyle({ index: idx }, {
      sphere: { scale: 0.45, color: '#f43f5e' }
    });
  });
  
  // Draw the lattice bounding box cylinders
  const m = structData.lattice;
  
  const origin = { x: 0, y: 0, z: 0 };
  const v1 = { x: m[0][0], y: m[0][1], z: m[0][2] };
  const v2 = { x: m[1][0], y: m[1][1], z: m[1][2] };
  const v3 = { x: m[2][0], y: m[2][1], z: m[2][2] };
  
  const v12 = { x: v1.x + v2.x, y: v1.y + v2.y, z: v1.z + v2.z };
  const v23 = { x: v2.x + v3.x, y: v2.y + v3.y, z: v2.z + v3.z };
  const v31 = { x: v3.x + v1.x, y: v3.y + v1.y, z: v3.z + v1.z };
  const v123 = { x: v1.x + v2.x + v3.x, y: v1.y + v2.y + v3.y, z: v1.z + v2.z + v3.z };
  
  const edges = [
    [origin, v1], [origin, v2], [origin, v3],
    [v1, v12], [v1, v31],
    [v2, v12], [v2, v23],
    [v3, v23], [v3, v31],
    [v12, v123], [v23, v123], [v31, v123]
  ];
  
  edges.forEach(edge => {
    viewer.addCylinder({
      start: edge[0],
      end: edge[1],
      radius: 0.03,
      color: '#f59e0b',
      fromCap: 1,
      toCap: 1
    });
  });
  
  viewer.zoomTo();
  viewer.render();
  
  element.viewerInstance = viewer;
}

function bindVisualizerTriggers(collidingIndices = []) {
  document.querySelectorAll(".structure-viewer-canvas").forEach((canvas) => {
    const content = decodeURIComponent(canvas.dataset.structureContent || "");
    if (content) {
      init3DmolViewer(canvas.id, content, 1, 1, 1, collidingIndices, "ball-and-stick");
    }
  });

  const getStyleAndRender = (fileName, na, nb, nc) => {
    const canvas = document.getElementById(`3dmol-${fileName}`);
    if (canvas) {
      const content = decodeURIComponent(canvas.dataset.structureContent || "");
      if (content) {
        const container = canvas.closest(".structure-visualizer-container");
        const style = container.querySelector(".select-3d-style")?.value || "ball-and-stick";
        init3DmolViewer(canvas.id, content, na, nb, nc, collidingIndices, style);
      }
    }
  };

  document.querySelectorAll(".btn-3d-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fileName = btn.dataset.3dTarget;
      const coords = btn.dataset.supercell.split(",").map(Number);
      
      const container = btn.closest(".structure-visualizer-container");
      container.querySelectorAll(".btn-3d-action").forEach(b => {
        b.style.background = "var(--bg-card)";
        b.style.borderColor = "rgba(255,255,255,0.1)";
        b.style.color = "#fff";
      });
      btn.style.background = "#6366f1";
      btn.style.borderColor = "#6366f1";

      container.querySelector(".input-3d-x").value = coords[0];
      container.querySelector(".input-3d-y").value = coords[1];
      container.querySelector(".input-3d-z").value = coords[2];

      getStyleAndRender(fileName, coords[0], coords[1], coords[2]);
    });
  });

  document.querySelectorAll(".btn-3d-custom-cell").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fileName = btn.dataset.3dTarget;
      const container = btn.closest(".structure-visualizer-container");
      
      container.querySelectorAll(".btn-3d-action").forEach(b => {
        b.style.background = "var(--bg-card)";
        b.style.borderColor = "rgba(255,255,255,0.1)";
        b.style.color = "#fff";
      });

      const na = parseInt(container.querySelector(".input-3d-x").value) || 1;
      const nb = parseInt(container.querySelector(".input-3d-y").value) || 1;
      const nc = parseInt(container.querySelector(".input-3d-z").value) || 1;

      getStyleAndRender(fileName, na, nb, nc);
    });
  });

  document.querySelectorAll(".select-3d-style").forEach((select) => {
    select.addEventListener("change", () => {
      const fileName = select.dataset.3dTarget;
      const container = select.closest(".structure-visualizer-container");
      
      const na = parseInt(container.querySelector(".input-3d-x").value) || 1;
      const nb = parseInt(container.querySelector(".input-3d-y").value) || 1;
      const nc = parseInt(container.querySelector(".input-3d-z").value) || 1;

      getStyleAndRender(fileName, na, nb, nc);
    });
  });
}
