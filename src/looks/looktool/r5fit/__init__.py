"""C2 native fitting with the provided raw-differential nonlinear operator.

The author's R5 response has been compared with existing C2 probe records;
this is not a newly calibrated C2 model or independent-scene acceptance.
Only native integers and a packed grid are exported, never the PC operator.
"""
from pathlib import Path
import json
import os
import sys
import types

ROOT=Path(__file__).resolve().parent
COMMIT='C2-mean-DE00-native-first-20261123-raw-differential-20261118'
IDENTITY=dict(schema='r5-measured-grid-response/1',preset='provided-raw-differential-20261118',model='ILCE-7CM2')

def initialize(threads=3,calibration=None):
    """Select CPU/CUDA explicitly; keep native objectives and integer acceptance."""
    for folder in (ROOT,ROOT/'upstream/R5ColorLab/amd',ROOT/'upstream/R5ColorLab/scripts'):
        if str(folder) not in sys.path:sys.path.insert(0,str(folder))
    device=os.environ.get('A7LOOK_FIT_DEVICE','cpu')
    if device not in ('cpu','cuda'):raise ValueError('Unsupported C2 fitting device')
    runtime=types.ModuleType('gpu_runtime')
    runtime.resolve_device=lambda:device
    runtime.available=lambda:True
    runtime.synchronize=lambda:torch.cuda.synchronize()if device=='cuda'else None
    runtime.empty_cache=lambda:torch.cuda.empty_cache()if device=='cuda'else None
    runtime.configure=lambda:None
    runtime.policy=lambda:dict(device=device,backend='PyTorch '+device+'; upstream mathematical objectives',threads=threads)
    sys.modules['gpu_runtime']=runtime
    import torch
    if device=='cuda'and not torch.cuda.is_available():raise RuntimeError('Requested CUDA accelerator is unavailable')
    torch.set_num_threads(threads)
    if device=='cuda':
        torch.set_float32_matmul_precision('highest')
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        # The GPU hosts' older OpenBLAS crashes inside the tall-Jacobian
        # DGESDD correction when the upstream progress wrapper enables ten
        # BLAS threads. Keep the same SVD/objective on one BLAS thread.
        from threadpoolctl import threadpool_limits
        threadpool_limits(limits=1,user_api='blas')
        import training_progress
        progress_init=training_progress.TrainingProgress.__init__
        if not getattr(progress_init,'c2_single_blas',False):
            def initialize_progress(self,path,total=0,gradient_workers=1):
                progress_init(self,path,total,gradient_workers=1)
            initialize_progress.c2_single_blas=True
            training_progress.TrainingProgress.__init__=initialize_progress
    # The GPU nodes have an older SciPy. Their fallback has identical finite
    # differences and bounds; only observational callback/worker dispatch was
    # added in 1.16. Keep this compatibility shim outside numerical objectives.
    import inspect,scipy.optimize
    original_ls=scipy.optimize.least_squares
    if 'callback'not in inspect.signature(original_ls).parameters:
        def least_squares(*args,callback=None,workers=None,**kwargs):return original_ls(*args,**kwargs)
        scipy.optimize.least_squares=least_squares
    from latent_response import LatentModel
    value=json.loads(Path(calibration or ROOT/'data/response.json').read_text(encoding='utf-8'))
    model=LatentModel(value,None,identity=IDENTITY)
    model.value['metadata']=dict(model='ILCE-7CM2',physical_scope='Provided R5 operator; C2 existing-probe comparison only')
    measured=types.ModuleType('measured_response')
    measured.SCHEMA=IDENTITY['schema']
    measured.is_measured=lambda v:isinstance(v,dict)and v.get('schema')==IDENTITY['schema']
    def get(v):
        if v!=IDENTITY:raise ValueError('C2 fitting requires the bundled C2 response')
        return model
    measured.get=get
    measured.require=lambda v:(get(v),v)[1]
    measured.hybrid_response=measured.default_response=lambda:IDENTITY.copy()
    sys.modules['measured_response']=measured
    import compute_backend
    compute_backend.WORKERS=threads
    import numpy as np
    original_render=getattr(compute_backend.render_native,'_c2_original',compute_backend.render_native)
    def render_flatfield(model,inputs):
        values=np.asarray(inputs)
        if values.ndim==3 and values.shape[1]==9 and np.all(values==values[:,:1,:]):
            # The source cohort repeats one post-SSCS integer RGB nine times.
            # Retain the original nine-point output and its averaging order.
            # The recovered hue frontend requires its original five-pixel
            # horizontal stencil. A constant patch has the same center output.
            once=original_render(model,values[:,:5,:])[:,2:3,:]
            return np.broadcast_to(once,values.shape).copy()
        return original_render(model,values)
    render_flatfield._c2_original=original_render
    compute_backend.render_native=render_flatfield
    import edit_parameter_context
    from windows_gamma import expand
    from windows_area import area_comp
    edit_parameter_context.expand_gamma=expand
    edit_parameter_context.RuntimeColor.area_comp=lambda self,p:area_comp(p,self.area_controls)
    import gpu_optimizer
    original=gpu_optimizer.StageObjective.__init__
    if not getattr(original,'c2_cpu',False):
        def init(self,*args,**kwargs):
            kwargs['device']=device;kwargs['dtype']=torch.float64 if device=='cpu'else torch.float32
            original(self,*args,**kwargs)
        init.c2_cpu=True
        gpu_optimizer.StageObjective.__init__=init
    return model

def context():
    import numpy as np
    from edit_color_pipeline import RuntimeColor
    with np.load(ROOT/'data/context.npz')as z:
        return RuntimeColor(*(z[k].tobytes()for k in ('runtime','raw','settings')),area_controls=z['area'].tobytes())

def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def metrics(target,prediction):
    import numpy as np
    e=np.abs(np.floor(np.clip(target,0,1)*255+.5)-np.floor(np.clip(prediction,0,1)*255+.5))
    return dict(points=len(e),rmse=float(np.sqrt(np.mean(e*e))),p95_channel=float(np.percentile(e,95)),
        p99_channel=float(np.percentile(e,99)),maximum_channel=float(e.max()),severe_gt30_points=int(np.count_nonzero(e.max(1)>30)))

def preflight():
    """Exercise packaged CPU/tensor inference, signed grid codec and gradients."""
    import numpy as np
    model=initialize()
    import torch
    from gpu_tensor import TensorTools
    from gpu_color import paired_tensor
    from residual_grid import pack,unpack
    rng=np.random.default_rng(20261110)
    rgb=np.r_[rng.uniform(.015,.985,(256,3)),np.linspace(0,1,17)[:,None]*np.ones((1,3))]
    table=rng.integers(-64,64,(405,3))
    if not np.array_equal(unpack(pack(table)),table):raise ValueError('Signed native grid roundtrip differs')
    tools=TensorTools('cpu',torch.float64)
    x=tools.tensor(rgb).requires_grad_(True)
    actual=paired_tensor(tools,x,tools.tensor(table),IDENTITY)
    error=float(np.max(np.abs(actual.detach().numpy()-model.predict_cpu(rgb,table))))
    if error>1e-12:raise ValueError('Nonlinear C2 CPU/tensor inference differs')
    actual.sum().backward()
    if not torch.isfinite(x.grad).all():raise ValueError('Nonfinite C2 response gradient')
    np.testing.assert_array_equal(model.predict_cpu(rgb,np.zeros((405,3))),rgb)
    return dict(model='ILCE-7CM2',upstream_commit=COMMIT,points=len(rgb),cpu_tensor_max_abs_error=error,
        gradients_finite=True,signed_grid_roundtrip=True,zero_grid_identity=True,camera_io=False)

def fit(target,output,*,evaluations=2000,starts=12,threads=3,previous=None,calibration=None):
    """Fit native color first, then a small residual grid using mean DE00."""
    from .native_first import fit as run
    return run(target,output,evaluations=evaluations,starts=starts,threads=threads,
        previous=previous,calibration=calibration)
