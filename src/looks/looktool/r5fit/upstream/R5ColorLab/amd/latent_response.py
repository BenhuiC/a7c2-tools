from gpu_runtime import resolve_device, available, synchronize, empty_cache
"""Frozen empirical chroma-domain operator; signed integer node coefficients.

Y,Cb,Cr -> (Y,Fcb(Cb),Fcr(Cr)); interpolate the grid here, add its
response here, then invert F. No fixed RGB response matrix is equivalent.
The positive/negative slopes are independently calibrated empirical terms.
"""
import numpy as np

class LatentModel:
    nonlinear_grid = True
    def __init__(self,value,sha256,identity=None):
        self.value=value;self.sha256=sha256;self.identity=identity
        if value['kernel']!='trilinear' or value['curve']['kind']!='lut':raise ValueError('Unsupported latent operator')
        self.matrix=np.array(value['matrix'],float);self.inverse=np.array(value['inverse'],float)
        self.affine=np.array(value['coordinate_affine'],float);self.knots=np.array(value['knots'],float)
        self.slopes=np.array(value['curve']['curves'],float)
        if (self.matrix.shape!=(3,3) or self.inverse.shape!=(3,3) or self.affine.shape!=(4,3)
            or self.slopes.shape!=(2,len(self.knots)-1) or not np.all(np.diff(self.knots)>0)
            or not np.all(self.slopes>0) or not all(np.isfinite(v).all() for v in (self.matrix,self.inverse,self.affine,self.knots,self.slopes))):
            raise ValueError('Invalid latent snapshot')
        self.encoded=np.array([self.encode(self.knots,c) for c in range(2)])
        self._constants={}

    def encode(self,x,c):
        widths=np.diff(self.knots)
        return (np.clip(np.asarray(x)[:,None]-self.knots[:-1],0,widths)-np.clip(-self.knots[:-1],0,widths))@self.slopes[c]

    def decode(self,x,c):return np.interp(x,self.encoded[c],self.knots)

    def coordinates(self,rgb):
        u=np.asarray(rgb,float)@self.matrix.T*255
        return np.c_[u[:,0]/255,self.encode(u[:,1],0)/255,self.encode(u[:,2],1)/255,np.ones(len(u))]@self.affine

    def stencil(self,rgb):
        from residual_grid import stencil
        q=self.coordinates(rgb);ids,w=stencil(q)
        return q,ids,w

    def predict_cpu(self,rgb,grid,clip=True):
        x=np.asarray(rgb,float);g=np.asarray(grid,float)
        if x.ndim!=2 or x.shape[1]!=3 or not np.isfinite(x).all():raise ValueError('Expected finite Nx3 RGB')
        if g.shape!=(405,3) or not np.isfinite(g).all():raise ValueError('Expected finite node-major405x3 grid')
        _,ids,w=self.stencil(x);d=(g[ids]*w[:,:,None]).sum(1)
        u=x@self.matrix.T*255;o=u.copy();o[:,0]+=d[:,0]
        for c in (1,2):o[:,c]=self.decode(self.encode(u[:,c],c-1)+d[:,c],c-1)
        out=o@self.inverse.T/255
        # A zero correction is the identity, including float rounding and LUT
        # endpoint support; nonzero responses retain the fitted endpoint rule.
        out=np.where(np.all(d==0,axis=1)[:,None],x,out)
        return np.clip(out,0,1) if clip else out

    predict=predict_cpu

    def constants(self,tools):
        key=(str(tools.device),str(tools.dtype))
        if key not in self._constants:
            self._constants[key]=tuple(tools.tensor(v) for v in (self.matrix,self.inverse,self.affine,self.knots,self.slopes,self.encoded))
        return self._constants[key]

    def encode_tensor(self,tools,x,c):
        _,_,_,k,s,_=self.constants(tools)
        # Prefix integral + local segment: O(N log K), unlike a dense Nx28
        # clipped-width expansion on every optimizer gradient.
        ek=self.constants(tools)[5][c]
        at=tools.torch.searchsorted(k,x.contiguous(),right=True).clamp(1,len(self.knots)-1)-1
        val=ek[at]+(x-k[at])*s[c,at]
        return tools.torch.where(x<=k[0],ek[0],tools.torch.where(x>=k[-1],ek[-1],val))

    def decode_tensor(self,tools,x,c):
        _,_,_,k,_,e=self.constants(tools);axis=e[c]
        at=tools.torch.searchsorted(axis,x.contiguous(),right=True).clamp(1,len(self.knots)-1)-1
        out=k[at]+(x-axis[at])*(k[at+1]-k[at])/(axis[at+1]-axis[at])
        return tools.torch.where(x<=axis[0],k[0],tools.torch.where(x>=axis[-1],k[-1],out))

    def coordinates_tensor(self,tools,x):
        m,_,a,_,_,_=self.constants(tools);u=x@m.T*255
        z=tools.torch.stack((u[:,0],self.encode_tensor(tools,u[:,1],0),self.encode_tensor(tools,u[:,2],1)),1)/255
        return z@a[:3]+a[3]

    def prepare_tensor(self,tools,x):
        from gpu_tensor import stencil_tensor
        m,_,a,_,_,_=self.constants(tools);u=x@m.T*255
        z=tools.torch.stack((u[:,0],self.encode_tensor(tools,u[:,1],0),self.encode_tensor(tools,u[:,2],1)),1)
        ids,w=stencil_tensor(tools,z/255@a[:3]+a[3])
        return dict(ids=ids,weights=w,encoded=z)

    def from_delta_tensor(self,tools,x,d,prepared,clip=True):
        z=prepared['encoded']+d
        u=tools.torch.stack((z[:,0],self.decode_tensor(tools,z[:,1],0),self.decode_tensor(tools,z[:,2],1)),1)
        out=u@self.constants(tools)[1].T/255
        # Straight-through identity rounding correction: preserves the grid
        # derivative at zero rather than killing every zero-initialized node.
        if not d.requires_grad:
            out=tools.torch.where((d==0).all(1)[:,None],x,out)
        return out.clamp(0,1) if clip else out

    def apply_tensor(self,tools,x,grid,prepared,clip=True):
        d=(grid[prepared['ids']]*prepared['weights'][:,:,None]).sum(1)
        return self.from_delta_tensor(tools,x,d,prepared,clip)

    def predict_tensor(self,tools,x,grid,clip=True):
        return self.apply_tensor(tools,x,grid,self.prepare_tensor(tools,x),clip)

    def response(self,*args):raise ValueError('Nonlinear latent response has no fixed RGB mixing matrix')
    def response_tensor(self,*args):return self.response()

    def probes(self,count=4096,seed=7):
        return np.random.default_rng(seed).random((count,3))

    def fit(self,base,target,weights,strength=0,*,iterations=600,device=None,continuous=False):
        import torch
        from scipy.optimize import minimize
        from gpu_tensor import TensorTools
        if device is None:
            from gpu_runtime import available
            device=resolve_device() if available() else 'cpu'
        tools=TensorTools(device,torch.float64 if device=='cpu' else torch.float32)
        x=tools.tensor(base);desired=tools.tensor(target).clamp(0,1);mass=tools.tensor(np.asarray(weights)/np.sum(weights))
        prepared=self.prepare_tensor(tools,x)
        from grid_regularization import get_penalty
        penalty=get_penalty(self.identity) if strength else None
        best=[float('inf'),np.zeros((405,3))];calls=0
        def objective(values):
            nonlocal calls
            grid=tools.tensor(values.reshape(405,3)).requires_grad_(True)
            p=self.apply_tensor(tools,x,grid,prepared)
            loss=((p-desired).square().sum(1)*mass).sum()
            if penalty:loss+=strength*penalty.tensor_raw_loss(tools,grid)
            loss.backward();value=float(loss.detach().cpu());grad=grid.grad.detach().cpu().numpy().astype(float).ravel();calls+=1
            if not np.isfinite(value) or not np.isfinite(grad).all():raise ValueError('Nonfinite latent grid fit')
            if value<best[0]:best[:]=[value,grid.detach().cpu().numpy().astype(float)]
            return value,grad
        before=objective(np.zeros(1215))[0]
        result=minimize(objective,np.zeros(1215),jac=True,method='L-BFGS-B',bounds=[(-64.,63.)]*1215,
            options=dict(maxiter=iterations,maxfun=iterations,maxls=25,ftol=1e-10))
        table=best[1]/256 if continuous else np.rint(best[1]).clip(-64,63).astype(np.int8)
        return table,dict(backend=device,solver='bounded exact latent nonlinear L-BFGS-B',iterations=int(result.nit),
            evaluations=calls,before=before,after=best[0],training_only=True,regularization=strength,converged=bool(result.success))
