"""Shared native Gamma with positive increments and unrestricted curvature."""
import numpy as np


class MonotoneGamma:
    def __init__(self,ctx,max_output=16383.):
        self.ctx=ctx;self.axis=np.asarray(ctx.axis,dtype=np.int64)
        self.max_output=float(max_output);self.parameter_count=len(self.axis)
        # Each interval contributes a nondecreasing ramp. Their nonnegative
        # mixture can have either sign of curvature on the original axis.
        width=np.diff(self.axis).astype(float)
        ramps=np.clip((self.axis[:,None]-self.axis[:-1])/width,0,1)
        self.basis=np.c_[ramps,np.zeros(len(self.axis))]

    def curve(self,values):
        values=np.asarray(values,dtype=float)
        mass=np.exp(values-values.max());mass/=mass.sum()
        return self.max_output*(self.basis@mass)

    def tensor_curve(self,torch,values):
        basis=torch.as_tensor(self.basis,device=values.device,dtype=values.dtype)
        return self.max_output*(basis@torch.softmax(values,dim=0))

    def encode(self,y14):
        y=np.clip(np.maximum.accumulate(y14),0,self.max_output)
        mass=np.r_[np.diff(y),max(self.max_output-y[-1],1e-8)]/self.max_output
        mass=np.maximum(mass,1e-12);mass/=mass.sum()
        return np.log(mass)

    def integer_curve(self,values):return self.quantize_raw(self.curve(values)*16)

    def quantize_raw(self,raw):
        from .gamma_admissibility import project
        y=np.minimum(262142,2*np.rint(np.asarray(raw)/2)).astype(np.int64)
        y=np.maximum.accumulate(y);y[0]=0
        return project(self.ctx,y)[0]

    def audit_even(self,raw):
        from .gamma_admissibility import legal
        y=np.asarray(raw)
        valid=(y.shape==self.axis.shape and np.isfinite(y).all() and y[0]==0 and
            np.all(y>=0) and np.all(y<=262142) and np.all(y%2==0) and np.all(np.diff(y)>=0))
        expanded=bool(valid and legal(self.ctx,y)[0])
        return dict(passed=expanded,monotone=bool(valid),expanded_monotone=expanded,
            concavity_required=False,zero_fixed=True,even_export_exact=bool(valid))
