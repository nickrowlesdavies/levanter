import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
W,H=1200,630
fig=plt.figure(figsize=(W/100,H/100),dpi=100)
ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(H,0); ax.axis("off")
X,Y=np.meshgrid(np.linspace(0,1,80),np.linspace(0,1,60))
cmap=LinearSegmentedColormap.from_list("lev",["#0ea5e9","#3b82f6","#6366f1"])
ax.imshow(X*0.7+Y*0.3,extent=[0,W,H,0],cmap=cmap,aspect="auto",interpolation="bilinear",zorder=0)
s,ox,oy=2.0,262,132
T=lambda x,y:(ox+x*s,oy+y*s)
def gust(p0,c1,c2,p3,sw,a):
    pth=Path([T(*p0),T(*c1),T(*c2),T(*p3)],[Path.MOVETO,Path.CURVE4,Path.CURVE4,Path.CURVE4])
    ax.add_patch(patches.PathPatch(pth,fill=False,edgecolor="white",lw=sw*s*0.72,alpha=a,capstyle="round",zorder=2))
gust((26,80),(50,70),(68,70),(90,76),8.5,0.5)
gust((26,60),(54,47),(76,47),(100,55),9,1.0)
gust((26,40),(46,32),(62,32),(80,37),8.5,0.82)
ax.add_patch(patches.PathPatch(Path([T(90,48),T(105,42),T(101,57)],[Path.MOVETO,Path.LINETO,Path.LINETO]),
             fill=False,edgecolor="white",lw=9*s*0.72,capstyle="round",joinstyle="round",zorder=2))
ax.text(500,282,"LEVANTER",color="white",fontsize=74,fontweight="heavy",va="baseline",ha="left")
ax.text(600,338,"M A R K E T S   ·   S I G N A L S   ·   I N S I G H T",color="#e8f1ff",fontsize=19,fontweight="semibold",va="baseline",ha="center")
ax.text(600,452,"Honest market intelligence, no hype.",color="white",fontsize=32,fontweight="medium",va="baseline",ha="center")
ax.text(600,508,"Volatility yes, direction no.",color="#dbeafe",fontsize=33,fontweight="bold",va="baseline",ha="center")
fig.savefig("brand/og.png",dpi=100)
print("og.png saved")
