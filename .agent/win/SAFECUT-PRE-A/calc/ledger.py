clip8=1.1184; muse=0.5889; base3=0.08; wscene=1.3601-clip8
L={"probes":6.00,"build WP1+WP4+WP5":8+6+6,"WP2 cap (plan 8x3x0.59=14.16)":15.00,
"WP7 cap (plan 3x1.12+5=8.36)":12.00,"test 12x3 + base3":12*round(clip8,2)*3+12*base3*3,
"recording code (PR #2)":12.00,"pilots cap":20.00,"public 6x3":18.00,"healthz Oct29-Nov4 7x0.134":7*0.1339}
for k,v in L.items(): print(f"{k:32s}{v:7.2f}")
t=sum(L.values()); print(f"TOTAL {t:.2f} headroom {150-t:.2f}")
print(f"wonder scene/run +{wscene:.4f}; 39 runs +{39*wscene:.2f}; pilots est {10*round(clip8,2):.2f}")
