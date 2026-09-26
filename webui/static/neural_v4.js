/* Animated neural brain and falling information rain for the approved UI. */
'use strict';

const MatrixRain = {
    canvas: null, ctx: null, columns: [], frame: 0, last: 0, reduced: false,
    init() {
        this.canvas = document.getElementById('matrixCanvas');
        this.ctx = this.canvas && this.canvas.getContext('2d');
        if (!this.ctx) return;
        this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.resize();
        window.addEventListener('resize', () => this.resize(), { passive: true });
        if (!this.reduced) this.animate(0);
        else this.draw(0);
    },
    resize() {
        const dpr = Math.min(devicePixelRatio || 1, 2);
        this.w = innerWidth; this.h = innerHeight;
        this.canvas.width = Math.round(this.w * dpr);
        this.canvas.height = Math.round(this.h * dpr);
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const count = Math.ceil(this.w / 24);
        this.columns = Array.from({ length: count }, (_, i) => ({
            x: i * 24 + 9,
            y: Math.random() * (this.h + 420) - 420,
            speed: 13 + Math.random() * 30,
            seed: Math.floor(Math.random() * 1000),
        }));
    },
    animate(now) {
        if (now - this.last >= 70 && !document.hidden) {
            this.last = now;
            this.draw(now / 1000);
        }
        this.frame = requestAnimationFrame((time) => this.animate(time));
    },
    draw(time) {
        const c = this.ctx;
        if (!c) return;
        c.clearRect(0, 0, this.w, this.h);
        c.font = '12px Consolas, monospace';
        c.textAlign = 'center';
        const glyphs = '0101011010011001';
        for (const col of this.columns) {
            const y = this.reduced ? col.y : (col.y + time * col.speed) % (this.h + 370) - 185;
            for (let k = 0; k < 17; k++) {
                const yy = y - k * 16;
                if (yy < 0 || yy > this.h) continue;
                const ch = glyphs[(col.seed + k + Math.floor(time * 2)) % glyphs.length];
                const alpha = k === 0 ? .72 : Math.max(.03, .31 - k * .019);
                c.fillStyle = k === 0 ? 'rgba(124,250,229,' + alpha + ')' : 'rgba(44,222,179,' + alpha + ')';
                c.fillText(ch, col.x, yy);
            }
        }
    },
};

Object.assign(NeuralStage, {
    brainNodes: [], brainEdges: [], signalAnchors: [], outline: null, lastFrame: 0, reduced: false,
    // The supplied brain artwork is the single source of the brain form.  Keep the
    // canvas only for the incoming/outgoing signal paths, not a second dot-cloud.
    showSyntheticBrain: false,
    init() {
        this.canvas = document.getElementById('neuralCanvas');
        this.ctx = this.canvas && this.canvas.getContext('2d');
        if (!this.ctx) return;
        this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.outline = new Path2D();
        const p = this.outline;
        p.moveTo(-.93, -.07);
        p.bezierCurveTo(-1.05,-.33,-.89,-.59,-.69,-.59);
        p.bezierCurveTo(-.68,-.84,-.39,-.93,-.2,-.78);
        p.bezierCurveTo(-.02,-.94,.25,-.88,.43,-.76);
        p.bezierCurveTo(.68,-.81,.91,-.59,.91,-.36);
        p.bezierCurveTo(1.12,-.19,1.04,.14,.87,.26);
        p.bezierCurveTo(.81,.52,.55,.62,.38,.54);
        p.bezierCurveTo(.23,.76,-.07,.75,-.19,.57);
        p.bezierCurveTo(-.46,.68,-.72,.53,-.8,.36);
        p.bezierCurveTo(-.98,.31,-1.04,.10,-.93,-.07);
        p.closePath();
        this.resize();
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(this.canvas.parentElement);
        MatrixRain.init();
        this.set('idle');
        if (this.reduced) this.draw(0);
        else this.animate(0);
    },
    resize() {
        if (!this.canvas || !this.ctx) return;
        const rect = this.canvas.getBoundingClientRect();
        const dpr = Math.min(devicePixelRatio || 1, 2);
        this.w = rect.width; this.h = rect.height;
        this.canvas.width = Math.max(1, Math.round(this.w * dpr));
        this.canvas.height = Math.max(1, Math.round(this.h * dpr));
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        let seed = 4917;
        const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
        this.brainNodes = [];
        for (let i = 0; i < 700; i++) {
            const x = rand() * 2 - 1, y = rand() * 1.55 - .87;
            if (this.ctx.isPointInPath(this.outline, x, y)) {
                this.brainNodes.push({ x, y, r:.55 + rand() * 1.05, phase:rand() * 6.28, violet:rand() > .6 });
            }
        }
        this.brainEdges = [];
        for (let i = 0; i < this.brainNodes.length; i++) {
            const a = this.brainNodes[i];
            const near = [];
            for (let j = 0; j < this.brainNodes.length; j++) {
                if (i === j) continue;
                const b = this.brainNodes[j];
                const d = (a.x-b.x)**2 + (a.y-b.y)**2;
                if (d < .028) near.push({ j, d });
            }
            near.sort((x,y) => x.d-y.d);
            for (const n of near.slice(0, 2)) if (n.j > i) this.brainEdges.push([i,n.j]);
        }
        this.updateSignalAnchors();
    },
    updateSignalAnchors() {
        const canvasRect = this.canvas.getBoundingClientRect();
        this.signalAnchors = [];
        for (const [selector, side] of [['.neural-hud-left .hud-chip', -1], ['.neural-hud-right .hud-chip', 1]]) {
            document.querySelectorAll(selector).forEach((chip, index) => {
                const rect = chip.getBoundingClientRect();
                if (!rect.width || !rect.height) return; // Hidden mobile HUD has no endpoints.
                this.signalAnchors.push({
                    side, index,
                    x: (side < 0 ? rect.right : rect.left) - canvasRect.left,
                    y: rect.top + rect.height / 2 - canvasRect.top,
                });
            });
        }
    },
    drawSignalLinks(c, t, speed, cx, cy, bw) {
        // Ten HUD nodes feed thirty fibers into two junctions beside the brain.
        c.save();
        c.lineCap = 'round';
        for (const node of this.signalAnchors) {
            const { side, index } = node;
            const hue = side < 0 ? '59,222,255' : '154,137,255';
            for (let lane = -1; lane <= 1; lane++) {
                const sx = node.x + side * -5;
                const sy = node.y + lane * 3.5;
                const ex = cx + side * bw * 1.48;
                const ey = cy + lane * 1.8 + (index - 2) * .55;
                const bend = Math.min(Math.abs(ex - sx) * .48, 92);
                const x1 = sx - side * bend, x2 = ex + side * bend;
                const y1 = sy, y2 = ey;
                const sample = (u) => {
                    const v = 1 - u;
                    const x = v*v*v*sx + 3*v*v*u*x1 + 3*v*u*u*x2 + u*u*u*ex;
                    const y = v*v*v*sy + 3*v*v*u*y1 + 3*v*u*u*y2 + u*u*u*ey;
                    const dx = 3*v*v*(x1-sx) + 6*v*u*(x2-x1) + 3*u*u*(ex-x2);
                    const dy = 3*v*v*(y1-sy) + 6*v*u*(y2-y1) + 3*u*u*(ey-y2);
                    const length = Math.hypot(dx, dy) || 1;
                    const envelope = Math.sin(Math.PI * u);
                    const wave = this.reduced ? 0 : envelope * (
                        Math.sin(u * 18 - t * speed * 2.5 + index * .8 + lane) * (3.8 + Math.abs(lane)) +
                        Math.sin(u * 35 + t * speed * 1.3 + index) * 1.2
                    );
                    return { x: x - dy / length * wave, y: y + dx / length * wave };
                };

                c.beginPath();
                for (let k = 0; k <= 46; k++) {
                    const p = sample(k / 46);
                    if (k) c.lineTo(p.x, p.y); else c.moveTo(p.x, p.y);
                }
                c.strokeStyle = `rgba(${hue},${lane === 0 ? .43 : .19})`;
                c.lineWidth = lane === 0 ? 1.25 : .7;
                c.shadowColor = side < 0 ? '#36dfff' : '#9a82ff';
                c.shadowBlur = lane === 0 ? 7 : 0;
                c.stroke();
                c.shadowBlur = 0;

                if (!this.reduced) {
                    for (let pulse = 0; pulse < 2; pulse++) {
                        const progress = (t * speed * .16 + index * .137 + lane * .21 + pulse * .5 + 3) % 1;
                        const p = sample(side < 0 ? progress : 1 - progress);
                        c.fillStyle = `rgba(${hue},${lane === 0 ? .96 : .68})`;
                        c.shadowColor = side < 0 ? '#75efff' : '#b6a3ff';
                        c.shadowBlur = lane === 0 ? 14 : 8;
                        c.beginPath(); c.arc(p.x, p.y, lane === 0 ? 2.1 : 1.25, 0, Math.PI * 2); c.fill();
                        c.shadowBlur = 0;
                    }
                }
            }
        }
        // A single, brighter bus carries the combined signal into/out of each hemisphere.
        for (const side of [-1, 1]) {
            if (!this.signalAnchors.some((node) => node.side === side)) continue;
            const hue = side < 0 ? '59,222,255' : '154,137,255';
            const startX = cx + side * bw * 1.48;
            const endX = cx + side * bw * .55;
            const sampleBus = (u) => ({
                x: startX + (endX - startX) * u,
                y: cy + (this.reduced ? 0 : Math.sin(u * 11 - t * speed * 2.7 + side) * Math.sin(Math.PI * u) * 3.3),
            });
            c.beginPath();
            for (let k = 0; k <= 40; k++) {
                const p = sampleBus(k / 40);
                if (k) c.lineTo(p.x, p.y); else c.moveTo(p.x, p.y);
            }
            c.strokeStyle = `rgba(${hue},.17)`;
            c.lineWidth = 15;
            c.shadowColor = side < 0 ? '#45dfff' : '#a18aff';
            c.shadowBlur = 20;
            c.stroke();
            c.shadowBlur = 0;
            c.strokeStyle = `rgba(${hue},.72)`;
            c.lineWidth = 4.5;
            c.stroke();
            c.strokeStyle = 'rgba(225,255,255,.86)';
            c.lineWidth = 1.15;
            c.stroke();

            c.fillStyle = side < 0 ? '#76f2ff' : '#b9a7ff';
            c.shadowColor = c.fillStyle;
            c.shadowBlur = 17;
            c.beginPath(); c.arc(startX, cy, 4.8, 0, Math.PI * 2); c.fill();
            if (!this.reduced) {
                for (let pulse = 0; pulse < 3; pulse++) {
                    const progress = (t * speed * .2 + pulse / 3) % 1;
                    const p = sampleBus(side < 0 ? progress : 1 - progress);
                    c.beginPath(); c.arc(p.x, p.y, 2.8, 0, Math.PI * 2); c.fill();
                }
            }
            c.shadowBlur = 0;
        }
        c.restore();
    },
    animate(now) {
        if (now - this.lastFrame > 28 && !document.hidden) {
            this.lastFrame = now;
            this.draw(now / 1000);
        }
        this.frame = requestAnimationFrame((time) => this.animate(time));
    },
    draw(t) {
        const c = this.ctx, w = this.w, h = this.h;
        if (!c || !w || !h) return;
        c.clearRect(0, 0, w, h);
        const active = ['running','thinking','tool'].includes(this.mode);
        const speed = active ? 1.65 : .66;
        const cx = w * .5, cy = h * .40;
        const bw = Math.min(w * .155, 160), bh = Math.min(h * .27, 92);
        this.drawSignalLinks(c, t, speed, cx, cy, bw);
        if (this.showSyntheticBrain) {
        c.save(); c.translate(cx,cy); c.scale(bw,bh);
        // A lumpy two-hemisphere silhouette anchors the constellation.
        const fill = c.createRadialGradient(-.08,-.2,.08,0,0,1.2);
        fill.addColorStop(0,'rgba(29,90,220,.09)'); fill.addColorStop(.66,'rgba(22,64,152,.05)'); fill.addColorStop(1,'rgba(20,88,200,.01)');
        c.fillStyle=fill; c.fill(this.outline);
        c.shadowColor='#3d8dff'; c.shadowBlur=13/bw; c.strokeStyle='rgba(95,161,255,.12)'; c.lineWidth=1/bw; c.stroke(this.outline); c.shadowBlur=0;
        // Folded neural ridges, clipped to the brain boundary.
        c.save(); c.clip(this.outline);
        for (let i=0;i<25;i++) {
            const yy=-.7+i*.056;
            c.beginPath();
            for (let k=0;k<57;k++) {
                const x=-1.05+k*.038;
                const y=yy+Math.sin(x*9+i*.81+t*speed*.7)*.028+Math.cos(x*18+i*.39)*.019;
                if (k) c.lineTo(x,y); else c.moveTo(x,y);
            }
            c.strokeStyle=i%3===0?'rgba(65,231,255,.13)':'rgba(128,113,255,.08)';
            c.lineWidth=.8/bw; c.stroke();
        }
        c.restore(); c.restore();
        // Stem lights connect the brain to the holographic platform.
        for (let i=0;i<20;i++) {
            const x=cx+(i-10)*1.5;
            const y1=cy+bh*.52+Math.abs(i-10)*.55;
            const y2=Math.min(h*.70,y1+42);
            c.beginPath(); c.moveTo(x,y1); c.quadraticCurveTo(x+Math.sin(i+t)*7,(y1+y2)/2,cx+(i-10)*.65,y2);
            c.strokeStyle='rgba(58,185,255,'+(.08+(i%4)*.04)+')'; c.lineWidth=.6; c.stroke();
        }
        // Synaptic network. Draw edges before the luminous particles.
        for (const edge of this.brainEdges) {
            const a=this.brainNodes[edge[0]], b=this.brainNodes[edge[1]];
            const shimmer=.55+.45*Math.sin(t*speed*2+a.phase);
            c.beginPath(); c.moveTo(cx+a.x*bw,cy+a.y*bh); c.lineTo(cx+b.x*bw,cy+b.y*bh);
            c.strokeStyle='rgba(68,158,255,'+(.11+.25*shimmer)+')'; c.lineWidth=.58; c.stroke();
        }
        for (const p of this.brainNodes) {
            const x=cx+p.x*bw, y=cy+p.y*bh;
            const pulse=.55+.45*Math.sin(t*speed*2+p.phase);
            c.fillStyle=p.violet?'rgba(158,124,255,'+(.44+.48*pulse)+')':'rgba(78,220,255,'+(.5+.48*pulse)+')';
            c.shadowColor=p.violet?'#886bff':'#3acfff'; c.shadowBlur=(active?10:6)*pulse;
            c.beginPath(); c.arc(x,y,p.r*(active?1.23:1),0,Math.PI*2); c.fill();
        }
        c.shadowBlur=0;
        }
        // The thought wave crossing the brain is the visual centerpiece.
        for (let j=0;j<4;j++) {
            c.beginPath();
            for (let k=0;k<=100;k++) {
                const u=k/100;
                const x=cx-bw*1.12+u*bw*2.24;
                const y=cy+Math.sin(u*13+t*speed*2+j*.48)*(12+j*3)+Math.sin(u*5+j)*4;
                if (k) c.lineTo(x,y); else c.moveTo(x,y);
            }
            c.strokeStyle=j===0?'rgba(170,255,255,.84)':'rgba(60,218,255,'+(.46-j*.08)+')';
            c.lineWidth=j===0?1.8:1; c.shadowColor='#3cecff'; c.shadowBlur=11; c.stroke();
        }
        c.shadowBlur=0;
        if (active) {
            const x=cx+Math.sin(t*speed)*bw*.8, y=cy+Math.sin(t*speed*2.2)*17;
            const glow=c.createRadialGradient(x,y,1,x,y,24);
            glow.addColorStop(0,'rgba(239,255,255,.95)'); glow.addColorStop(.22,'rgba(92,236,255,.68)'); glow.addColorStop(1,'rgba(92,236,255,0)');
            c.fillStyle=glow; c.beginPath(); c.arc(x,y,24,0,Math.PI*2); c.fill();
        }
    },
});
