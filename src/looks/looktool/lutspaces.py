"""Explicit CUBE transfer/gamut adaptation into the existing C2 SDR target.

Published transfer functions / primaries follow Colour Science v0.4.6 and its
vendor references (BSD-3-Clause notice in licenses/). M4 compatibility tables
are separately attributed approximations, not sensor calibration or gamut data.
"""
from functools import lru_cache
from pathlib import Path
import json,re
import numpy as np

D65=(.3127,.3290)
PRIMARIES={
 'rec709':((.64,.33),(.30,.60),(.15,.06)),
 'p3':((.68,.32),(.265,.69),(.15,.06)),
 'adobe':((.64,.33),(.21,.71),(.15,.06)),
 'rec2020':((.708,.292),(.170,.797),(.131,.046)),
 'sgamut':((.73,.28),(.14,.855),(.10,-.05)),
 'sgamut3cine':((.766,.275),(.225,.8),(.089,-.087)),
 'cinema':((.74,.27),(.17,1.14),(.08,-.10)),
 'vgamut':((.73,.28),(.165,.84),(.10,-.03)),
 'awg3':((.684,.313),(.221,.848),(.0861,-.102)),
 'awg4':((.7347,.2653),(.1424,.8576),(.0991,-.0308)),
 'dgamut':((.71,.31),(.21,.88),(.09,-.08)),
}
# key, label, transfer, primaries. All listed spaces share the D65 white.
PROFILES=[
 ('sony-st-srgb','Sony ST / sRGB','srgb','rec709'),
 ('rec709','Rec.709','rec709','rec709'),
 ('gamma24-rec709','Gamma 2.4 / Rec.709','gamma24','rec709'),
 ('linear-srgb','Linear / Rec.709','linear','rec709'),
 ('display-p3','Display P3','srgb','p3'),
 ('adobe-rgb','Adobe RGB (1998)','adobe','adobe'),
 ('rec2020','Rec.2020','rec709','rec2020'),
 ('slog3-sgamut3cine','Sony S-Log3 / S-Gamut3.Cine','slog3','sgamut3cine'),
 ('slog3-sgamut3','Sony S-Log3 / S-Gamut3','slog3','sgamut'),
 ('slog2-sgamut','Sony S-Log2 / S-Gamut','slog2','sgamut'),
 ('clog2-cinema','Canon Log2 / Cinema Gamut','clog2','cinema'),
 ('clog3-cinema','Canon Log3 / Cinema Gamut','clog3','cinema'),
 ('nlog-rec2020','Nikon N-Log / Rec.2020','nlog','rec2020'),
 ('vlog-vgamut','Panasonic V-Log / V-Gamut','vlog','vgamut'),
 ('flog-fgamut','Fujifilm F-Log / F-Gamut','flog','rec2020'),
 ('flog2-fgamut','Fujifilm F-Log2 / F-Gamut','flog2','rec2020'),
 ('logc3-awg3','ARRI LogC3 EI800 / Wide Gamut 3','logc3','awg3'),
 ('logc4-awg4','ARRI LogC4 / Wide Gamut 4','logc4','awg4'),
 ('dlog-dgamut','DJI D-Log / D-Gamut','dlog','dgamut'),
 ('pq-rec2020','PQ ST.2084 / Rec.2020 (SDR white 100 nit)','pq','rec2020'),
 ('hlg-rec2020','HLG / Rec.2020 (75% reference white)','hlg','rec2020'),
]
ALIASES={'srgb':'sony-st-srgb','display':'sony-st-srgb','bt709':'rec709','linear':'linear-srgb',
 'slog3':'slog3-sgamut3cine','slog2':'slog2-sgamut','clog2':'clog2-cinema','clog3':'clog3-cinema',
 'nlog':'nlog-rec2020','vlog':'vlog-vgamut','flog':'flog-fgamut','flog2':'flog2-fgamut',
 'logc3':'logc3-awg3','logc4':'logc4-awg4','dlog':'dlog-dgamut','pq':'pq-rec2020','hlg':'hlg-rec2020'}

@lru_cache(maxsize=1)
def compatibility():
    path=Path(__file__).resolve().parents[1]/'assets/lut-compat-curves.json'
    return json.loads(path.read_text(encoding='utf-8'))['curves']

def options():
    rows=[dict(key=k,label=label,approximate=False)for k,label,_,_ in PROFILES]
    rows += [dict(key='m4-'+k,label='M4 compatibility / '+k+' (17-point approximation)',approximate=True)
             for k in compatibility()]
    return dict(inputs=rows,outputs=[row for row in rows if row['key']in
         ('sony-st-srgb','rec709','gamma24-rec709','linear-srgb','display-p3','adobe-rgb','rec2020','pq-rec2020','hlg-rec2020')],
         default_input='sony-st-srgb',default_output='sony-st-srgb',
         scope='SDR still-photo look approximation; this does not enable a camera video Log mode')

def resolve(key):
    key=ALIASES.get(key,key)
    for row in PROFILES:
        if row[0]==key:return row
    if key.startswith('m4-')and key[3:]in compatibility():return key,'M4 compatibility '+key[3:],key,'rec709'
    raise ValueError('Unsupported CUBE space: '+str(key))

@lru_cache(maxsize=16)
def matrix(gamut):
    xy=np.asarray(PRIMARIES[gamut],dtype=float)
    xyz=np.stack((xy[:,0]/xy[:,1],np.ones(3),(1-xy.sum(1))/xy[:,1]))
    x,y=D65;white=np.array([x/y,1,(1-x-y)/y])
    return xyz*np.linalg.solve(xyz,white)[None,:]

def _log(v):return np.log10(np.maximum(v,1e-30))
def _pow(v,n):return np.sign(v)*np.abs(v)**n

def encode(value,curve):
    x=np.asarray(value,dtype=float)
    if curve.startswith('m4-'):
        display=encode(x,'srgb');return np.interp(display,np.linspace(0,1,17),compatibility()[curve[3:]])
    if curve=='linear':return x
    if curve=='srgb':return np.where(x<=.0031308,x*12.92,1.055*np.maximum(x,0)**(1/2.4)-.055)
    if curve=='rec709':return np.where(x<.018,4.5*x,1.099*np.maximum(x,0)**.45-.099)
    if curve=='gamma24':return _pow(x,1/2.4)
    if curve=='adobe':return _pow(x,256/563)
    if curve=='slog3':return np.where(x>=.01125,(420+261.5*_log((x+.01)/.19))/1023,(95+x*(171.2102946929-95)/.01125)/1023)
    if curve=='slog2':
        z=x*155/219/.9
        y=np.where(z>=0,.432699*_log(z+.037584)+.646596,5*z+.030001222851889303)
        return (y*876+64)/1023
    if curve=='clog2':
        z=x/.9;return np.sign(z)*.24136077*_log(1+87.09937546*np.abs(z))+.092864125
    if curve=='clog3':
        z=x/.9
        low=-(10**((.12783901-.097465473)/.36726845)-1)/14.98325
        high=(.15277891-.12512219)/1.9754798
        return np.where(z<low,-.36726845*_log(1-14.98325*z)+.12783901,
                        np.where(z<=high,1.9754798*z+.12512219,.36726845*_log(1+14.98325*z)+.12240537))
    if curve=='nlog':return np.where(x<.328,650/1023*np.cbrt(x+.0075),150/1023*np.log(np.maximum(x,1e-30))+619/1023)
    if curve=='vlog':return np.where(x<.01,5.6*x+.125,.241514*_log(x+.00873)+.598206)
    if curve in ('flog','flog2'):
        cut,a,b,c,d,e,f=(.00089,.555556,.009468,.344676,.790453,8.735631,.092864)if curve=='flog'else(.000889,5.555556,.064829,.245281,.384316,8.799461,.092864)
        return np.where(x<cut,e*x+f,c*_log(a*x+b)+d)
    if curve=='logc3':return np.where(x>.010591,.247190*_log(5.555556*x+.052272)+.385537,5.367655*x+.092809)
    if curve=='logc4':
        a=(2**18-16)/117.45;b=928/1023;c=95/1023
        s=7*np.log(2)*2**(7-14*c/b)/(a*b);t=(2**(6-14*c/b)-64)/a
        return np.where(x>=t,(np.log2(np.maximum(a*x+64,1e-30))-6)/14*b+c,(x-t)/s)
    if curve=='dlog':return np.where(x<=.0078,6.025*x+.0929,.256663*_log(.9892*x+.0108)+.584555)
    if curve=='pq':
        y=np.maximum(x,0)/100;m1=2610/16384;m2=2523/32
        return ((3424/4096+2413/128*y**m1)/(1+2392/128*y**m1))**m2
    if curve=='hlg':
        a=.17883277;b=1-4*a;c=.5-a*np.log(4*a)
        white=(np.exp((.75-c)/a)+b)/12;y=np.maximum(x,0)*white
        return np.where(y<=1/12,np.sqrt(3*y),a*np.log(np.maximum(12*y-b,1e-30))+c)
    raise ValueError(curve)

def decode(value,curve):
    x=np.asarray(value,dtype=float)
    if curve.startswith('m4-'):
        display=np.interp(x,compatibility()[curve[3:]],np.linspace(0,1,17));return decode(display,'srgb')
    if curve=='linear':return x
    if curve=='srgb':return np.where(x<=.04045,x/12.92,((np.maximum(x,0)+.055)/1.055)**2.4)
    if curve=='rec709':return np.where(x<.081,x/4.5,((np.maximum(x,0)+.099)/1.099)**(1/.45))
    if curve=='gamma24':return _pow(x,2.4)
    if curve=='adobe':return _pow(x,563/256)
    if curve=='pq':
        p=np.maximum(x,0)**(32/2523)
        return (np.maximum(p-3424/4096,0)/np.maximum(2413/128-2392/128*p,1e-30))**(16384/2610)*100
    if curve=='hlg':
        a=.17883277;b=1-4*a;c=.5-a*np.log(4*a)
        scene=np.where(x<=.5,x*x/3,(np.exp((x-c)/a)+b)/12)
        white=(np.exp((.75-c)/a)+b)/12
        return scene/white
    if curve=='slog3':return np.where(x>=171.2102946929/1023,10**((x*1023-420)/261.5)*.19-.01,(x*1023-95)*.01125/(171.2102946929-95))
    if curve=='slog2':
        y=(x*1023-64)/876;cut=.432699*np.log10(.037584)+.646596
        return np.where(y>=cut,10**((y-.646596)/.432699)-.037584,(y-.030001222851889303)/5)*.9*219/155
    if curve=='clog2':
        y=x-.092864125;return np.sign(y)*(10**(np.abs(y)/.24136077)-1)/87.09937546*.9
    if curve=='clog3':return np.where(x<.097465473,-(10**((.12783901-x)/.36726845)-1)/14.98325,np.where(x<=.15277891,(x-.12512219)/1.9754798,(10**((x-.12240537)/.36726845)-1)/14.98325))*.9
    if curve=='nlog':return np.where(x<452/1023,(x/(650/1023))**3-.0075,np.exp((x-619/1023)/(150/1023)))
    if curve=='vlog':return np.where(x<.181,(x-.125)/5.6,10**((x-.598206)/.241514)-.00873)
    if curve in ('flog','flog2'):
        cut,a,b,c,d,e,f=(.100537775223865,.555556,.009468,.344676,.790453,8.735631,.092864)if curve=='flog'else(.100686685370811,5.555556,.064829,.245281,.384316,8.799461,.092864)
        return np.where(x<cut,(x-f)/e,(10**((x-d)/c)-b)/a)
    if curve=='logc3':return np.where(x>5.367655*.010591+.092809,(10**((x-.385537)/.247190)-.052272)/5.555556,(x-.092809)/5.367655)
    if curve=='logc4':
        a=(2**18-16)/117.45;b=928/1023;c=95/1023
        s=7*np.log(2)*2**(7-14*c/b)/(a*b);t=(2**(6-14*c/b)-64)/a
        return np.where(x>=0,(2**(14*((x-c)/b)+6)-64)/a,x*s+t)
    if curve=='dlog':return np.where(x<=6.025*.0078+.0929,(x-.0929)/6.025,(10**((x-.584555)/.256663)-.0108)/.9892)
    raise ValueError(curve)

def convert(rgb,source,destination):
    source=resolve(source);destination=resolve(destination)
    values=np.asarray(rgb,dtype=float)
    if source[0]==destination[0]:return values.copy()
    linear=decode(values,source[2])
    if source[3]!=destination[3]:linear=linear@np.linalg.solve(matrix(destination[3]),matrix(source[3])).T
    return encode(linear,destination[2])

def suggest(path):
    """Filename/TITLE suggestions only; no inverse-gray fit can prove gamut."""
    path=Path(path);head=path.read_text(encoding='utf-8-sig',errors='replace')[:8192]
    titles=' '.join(line for line in head.splitlines()if line.strip().upper().startswith(('TITLE','#')))
    text=(path.name+' '+titles).lower().replace('_',' ').replace('-','').replace(' ','')
    hints=[('flog2c','m4-flog2c'),('flog2','flog2-fgamut'),('flog','flog-fgamut'),
      ('dlogm','m4-dlogm'),('dlog2','m4-dlog2'),('dlog','dlog-dgamut'),('ilog','m4-ilog'),('llog','m4-llog'),
      ('logc4','logc4-awg4'),('logc3','logc3-awg3'),('clog3','clog3-cinema'),('canonlog3','clog3-cinema'),
      ('clog2','clog2-cinema'),('canonlog2','clog2-cinema'),('nlog','nlog-rec2020'),('vlog','vlog-vgamut'),
      ('slog2','slog2-sgamut'),('slog3','slog3-sgamut3cine')]
    key=next((key for hint,key in hints if hint in text),'sony-st-srgb')
    if key=='slog3-sgamut3cine'and 'sgamut3'in text and 'cine'not in text:key='slog3-sgamut3'
    return dict(input_space=key,output_space='sony-st-srgb',suggestion_only=True,
                note='Confirm both input and output; names and neutral-axis behavior cannot establish the LUT gamut.')

class CubeTarget:
    def __init__(self,path,input_space='sony-st-srgb',output_space='srgb',bridge=None):
        from .references import Cube
        self.cube=Cube(path);self.bridge=Cube(bridge)if bridge else None
        self.input_space=input_space;self.output_space=resolve(output_space)[0]
        if not bridge:resolve(input_space)
    def sample(self,rgb):
        entering=self.bridge.sample(rgb)if self.bridge else convert(rgb,'sony-st-srgb',self.input_space)
        value=self.cube.sample(entering)
        return convert(value,self.output_space,'sony-st-srgb')
    def contract(self):
        return dict(input_space=self.input_space,output_space=self.output_space,bridge_used=self.bridge is not None,
            target_space='sony-st-srgb',wide_gamut_matrix=not self.input_space.startswith('m4-')and self.bridge is None,
            compatible_curve_approximation=self.input_space.startswith('m4-'),
            scene_scope='Normalized SDR ST/sRGB reference, not reconstructed scene highlight exposure',
            hdr_scope='PQ relative to 100 nit; HLG relative to 75% code; SDR out-of-range components clipped',
            Lightroom_reference_used=False,automatic_Adobe_profile_generated=False)
