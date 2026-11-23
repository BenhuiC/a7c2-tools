"""Native-first C2 fitting with a shared mean-DE00 objective and a small grid.

Continuous proposals use the existing differentiable native/latent renderers.
Acceptance and selection use the original integer C2 builder and CPU operator.
"""
import base64,copy,json,time
from pathlib import Path
import numpy as np
from . import de00_objective as objective
from .monotone_gamma import MonotoneGamma


def fit(target,output,*,evaluations=2000,starts=12,threads=3,previous=None,calibration=None):
    from . import ROOT,IDENTITY,initialize,context,save,metrics
    from scipy.optimize import minimize
    import torch
    model=initialize(threads,calibration)
    from edit_parameter_context import ParameterContext
    from fit_anchor_native import SmoothNative,vector_for,training_plan
    from optimizer_policy import refine_native
    from compute_backend import render_native
    from patch_sampling import center_mean
    from gpu_tensor import TensorTools
    from apple_gpu import SmoothGPU
    from residual_grid import pack,unpack
    from gpu_color import paired_tensor
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    profile=json.loads((ROOT/'formal_profile.json').read_text(encoding='utf-8'))
    settings=profile['settings'];device=__import__('os').environ.get('A7LOOK_FIT_DEVICE','cpu')
    if evaluations<1 or starts<1:raise ValueError('Positive fitting budgets required')
    with np.load(ROOT/'data/inputs.npz')as z:data={k:z[k].copy()for k in z.files}
    target=np.asarray(target,dtype=float)
    if target.shape!=(len(data['input']),3)or not np.isfinite(target).all():raise ValueError('C2 target array differs')
    request=dict(algorithm='C2-mean-DE00-native-first-S-gamma/1',evaluations=evaluations,
        starts=starts,settings=settings,group_weights=profile['options']['group_weights'],
        sampling=profile['options']['search_options'],
        previous_parameters=previous['edit_native']['fitted']if previous is not None else None,
        previous_grid=previous['table_base64']if previous is not None else None,
        response=json.loads(Path(calibration or ROOT/'data/response.json').read_text(encoding='utf-8')))
    for source,name in ((ROOT/'data/context.npz','input-context.npz'),(ROOT/'data/inputs.npz','input-cohort.npz')):
        frozen=output/name;content=source.read_bytes()
        if frozen.exists()and frozen.read_bytes()!=content:raise ValueError('Saved native fitting inputs changed')
        if not frozen.exists():frozen.write_bytes(content)
    pairs=output/'pairs.npz'
    if (output/'run-input.json').exists():
        if json.loads((output/'run-input.json').read_text(encoding='utf-8'))!=request:raise ValueError('Saved training options differ')
        with np.load(pairs)as z:
            if not np.array_equal(z['target'],target):raise ValueError('Saved fit target differs')
    else:
        save(output/'run-input.json',request)
        np.savez_compressed(pairs,target=target)
    if (output/'complete.json').exists():
        return json.loads((output/'parameters.json').read_text(encoding='utf-8')),(output/'grid.payload').read_bytes(),json.loads((output/'complete.json').read_text(encoding='utf-8'))
    checkpoint=output/'checkpoint.json'
    resume=json.loads(checkpoint.read_text(encoding='utf-8'))if checkpoint.exists()else{}
    started=time.perf_counter();events=resume.get('events',[])
    from training_progress import TrainingProgress
    tracker=TrainingProgress(output/'training_progress.json',starts+1+settings['grid_rounds']+2*settings['rounds'])
    tracker.value['round']=resume.get('native_done',0)+int(resume.get('integer_done',False))+resume.get('grid_done',0)+2*resume.get('joint_done',0)
    def progress(**row):
        row=dict(seconds=round(time.perf_counter()-started,3),**row)
        if row.get('stage')!=tracker.value.get('stage'):tracker.value['round']+=1
        tracker.update(**row,state='running')
        with(output/'progress.jsonl').open('a',encoding='utf-8')as stream:stream.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
    split=data['split'];random_train=np.flatnonzero((split=='train')&(data['anchor_index']<0)&(data['sector16_index']<0))
    train,_,_,weights=training_plan(split,data['anchor_index'],profile['options']['group_weights'],
        data['sector16_index'],data['baseline_tonal_index'],random_train,data['sample_kind'],profile['options']['search_options'])
    valid=np.flatnonzero(split=='valid')
    ctx=ParameterContext(context());ctx.gamma_shape=MonotoneGamma(ctx)
    shape=ctx.gamma_shape
    smooth=SmoothNative(ctx,data['input'][train])
    tools=TensorTools(device,torch.float64 if device=='cpu'else torch.float32)
    native_gpu=SmoothGPU(smooth,device=device,dtype=tools.dtype)
    desired=tools.tensor(target[train]);mass=tools.tensor(weights/weights.sum())
    lower=np.r_[np.full(4,-.999),np.zeros(4),np.full(96,-7.99),np.full(128,-28.)]
    upper=np.r_[np.full(4,.996),np.full(4,3.98),np.full(96,7.99),np.full(128,28.)]
    output_weight=settings['grid_output_weight'];node_weight=settings['grid_node_weight']

    def fields(params):
        return dict(matrix_780f_hex=params['matrix_payload'].hex(),cc1_direct_raw=params['cc1'].tolist(),gamma_7806_y=params['gamma_y'].tolist())
    def params_from_fields(value):
        return dict(matrix_payload=bytes.fromhex(value['matrix_780f_hex']),cc1=np.asarray(value['cc1_direct_raw']),gamma_y=np.asarray(value['gamma_7806_y']))
    def vector(params):
        other=ParameterContext(ctx.build(**params));other.gamma_shape=shape
        return np.clip(vector_for(other),lower,upper)
    def render(params):
        return center_mean(render_native(ctx.build(**params),data['input']))/16383
    def score(base,grid,rows=train,weighted=True):
        native=np.asarray(base)[rows];prediction=model.predict_cpu(native,grid)
        color=objective.mean(prediction,target[rows],weights if weighted else None)
        penalty=objective.grid_penalty(native,prediction,grid,output_weight,node_weight)
        return dict(data=color,grid_penalty=penalty,total=color+penalty)
    def validation(base,grid):
        native=base[valid];prediction=model.predict_cpu(native,grid)
        return float(objective.distances(prediction,target[valid]).mean()+
            objective.grid_penalty(native,prediction,grid,output_weight,node_weight))
    def make_state(params,grid,label):
        base=render(params)
        return dict(params=params,grid=unpack(pack(grid)),base=base,label=label,
            validation=validation(base,grid))
    zero=np.zeros((405,3),dtype=np.int8)
    factory=dict(matrix_payload=ctx.payload,cc1=ctx.cc1.copy(),gamma_y=shape.quantize_raw(ctx.gamma_y))
    seeds=[factory]
    reference=None
    if previous is not None:
        q=previous['edit_native']['fitted'];params=params_from_fields(q)
        params['gamma_y']=shape.quantize_raw(params['gamma_y'])
        seeds.insert(0,params)
        reference=make_state(params,unpack(base64.b64decode(previous['table_base64'])),'previous')
    chosen_native=min((make_state(p,zero,'native-seed-'+str(i))for i,p in enumerate(seeds)),key=lambda s:s['validation'])
    def stored(state):
        return dict(parameters=fields(state['params']),grid_base64=base64.b64encode(pack(state['grid'])).decode(),label=state['label'])
    def restored(state):
        return make_state(params_from_fields(state['parameters']),unpack(base64.b64decode(state['grid_base64'])),state['label'])
    if resume.get('native'):chosen_native=restored(resume['native'])
    native_done=resume.get('native_done',0);integer_done=resume.get('integer_done',False)
    grid_done=resume.get('grid_done',0);joint_done=resume.get('joint_done',0)
    def persist(current=None,chosen=None):
        value=dict(native_done=native_done,integer_done=integer_done,grid_done=grid_done,joint_done=joint_done,
            native=stored(chosen_native),events=events)
        if current is not None:value['current']=stored(current)
        if chosen is not None:value['chosen']=stored(chosen)
        temporary=output/'checkpoint.tmp.json';save(temporary,value);temporary.replace(checkpoint)
    rng=np.random.default_rng(20261123)

    def optimize_native(seed,grid,label,budget):
        initial=vector(seed);seed_base=render(seed);before=score(seed_base,grid)
        fixed=tools.tensor(grid);best=[float('inf'),initial.copy()];calls=0
        def loss(v):
            base=native_gpu.render(v)/16383
            prediction=paired_tensor(tools,base,fixed,IDENTITY)
            return objective.tensor_mean(tools,prediction,desired,mass)+objective.tensor_grid_penalty(tools,base,prediction,fixed,output_weight,node_weight)
        # Check the same smooth expression on CPU and tensor paths once per
        # parameterization; exact integer acceptance is a separate operation.
        smooth_base=smooth.render(initial)/16383
        smooth_prediction=model.predict_cpu(smooth_base,grid)
        expected=objective.mean(smooth_prediction,target[train],weights)+objective.grid_penalty(smooth_base,smooth_prediction,grid,output_weight,node_weight)
        actual=float(loss(tools.tensor(initial)).detach().cpu())
        if abs(expected-actual)>max(2e-3,abs(expected)*3e-3):raise ValueError('Native mean-DE00 CPU/tensor objective mismatch')
        class BudgetReached(Exception):pass
        def fg(values):
            nonlocal calls
            if calls>=budget:raise BudgetReached()
            v=tools.tensor(values).requires_grad_(True);value=loss(v);value.backward();calls+=1
            scalar=float(value.detach().cpu());gradient=v.grad.detach().cpu().numpy().astype(float)
            if not np.isfinite(scalar)or not np.isfinite(gradient).all():raise ValueError('Nonfinite native mean-DE00 gradient')
            if scalar<best[0]:best[:]=[scalar,values.copy()]
            if calls%25==0:progress(stage=label,evaluations=calls,max_evaluations=budget,loss=scalar)
            return scalar,gradient
        try:
            result=minimize(fg,initial,jac=True,method='L-BFGS-B',bounds=list(zip(lower,upper)),
                options=dict(maxfun=budget,maxiter=budget,maxls=25,ftol=1e-10,gtol=1e-6,maxcor=20))
            message=str(result.message)
        except BudgetReached:message='evaluation budget reached'
        best_state=make_state(seed,grid,label+'-seed');selected=before;attempts=[]
        for alpha in (1.,.75,.5,.25,.125):
            candidate=smooth.params(initial+alpha*(best[1]-initial))
            try:state=make_state(candidate,grid,label)
            except ValueError as error:
                if str(error)!='MainGamma must be signed and monotone on positive input':raise
                continue
            result=score(state['base'],grid);attempts.append(dict(alpha=alpha,**result))
            if result['total']<selected['total']-1e-9:best_state,selected=state,result
        audit=dict(stage=label,calls=calls,solver_message=message,before=before,after=selected,
            attempts=attempts,gamma_frozen=False,integer_acceptance=True,objective='mean DeltaE00 + small grid correction')
        events.append(audit);progress(**audit)
        return best_state

    for index in range(starts):
        seed=copy.deepcopy(seeds[index%len(seeds)])
        if index>=len(seeds):
            v=vector(seed);v[:8]+=rng.normal(0,.025,8)
            v[8:104]+=rng.normal(0,.035,96)
            v[104:]+=np.convolve(rng.normal(0,.08,128),np.ones(5)/5,mode='same')
            seed=smooth.params(np.clip(v,lower,upper))
        if index<native_done:continue
        state=optimize_native(seed,zero,'native-start-'+str(index+1),evaluations)
        if state['validation']<chosen_native['validation']:chosen_native=copy.deepcopy(state)
        save(output/'native-progress.json',dict(completed_starts=index+1,best_validation=chosen_native['validation']))
        save(output/'native-parameters.json',fields(chosen_native['params']))
        native_done=index+1;persist()
    if not integer_done:
        refined,audit=refine_native(ctx,chosen_native['params'],data['input'][train],target[train],weights,None,
            sweeps=settings['native_integer_sweeps'],objective_rows=objective.rows,
            progress=lambda **row:progress(stage='native-integer-refinement',**row))
        refined_state=make_state(refined,zero,'native-integer-refined')
        audit=dict(stage='native-integer-refinement',**audit);events.append(audit);progress(**audit)
        if refined_state['validation']<chosen_native['validation']:chosen_native=refined_state
        save(output/'native-parameters.json',fields(chosen_native['params']))
        integer_done=True;persist()
    current=restored(resume['current'])if resume.get('current')else chosen_native

    def optimize_grid(base,grid,label,budget):
        from stack_objective import GridRenderer
        renderer=GridRenderer(tools,base[train],model);native=tools.tensor(base[train])
        best=[float('inf'),np.asarray(grid,dtype=float).copy()];calls=0
        def loss(table):
            prediction=renderer(table)
            return objective.tensor_mean(tools,prediction,desired,mass)+objective.tensor_grid_penalty(tools,native,prediction,table,output_weight,node_weight)
        expected=score(base,grid)['total'];actual=float(loss(tools.tensor(grid)).detach().cpu())
        if abs(expected-actual)>max(2e-3,abs(expected)*3e-3):raise ValueError('Grid mean-DE00 CPU/tensor objective mismatch')
        class BudgetReached(Exception):pass
        def fg(values):
            nonlocal calls
            if calls>=budget:raise BudgetReached()
            table=tools.tensor(values.reshape(405,3)).requires_grad_(True);value=loss(table);value.backward();calls+=1
            scalar=float(value.detach().cpu());gradient=table.grad.detach().cpu().numpy().astype(float)
            if not np.isfinite(scalar)or not np.isfinite(gradient).all():raise ValueError('Nonfinite grid mean-DE00 gradient')
            if scalar<best[0]:best[:]=[scalar,values.reshape(405,3).copy()]
            if calls%25==0:progress(stage=label,evaluations=calls,max_evaluations=budget,loss=scalar)
            return scalar,gradient.ravel()
        try:
            result=minimize(fg,np.asarray(grid,dtype=float).ravel(),jac=True,method='L-BFGS-B',bounds=[(-64,63)]*1215,
                options=dict(maxfun=budget,maxiter=budget,maxls=25,ftol=1e-10,gtol=1e-6,maxcor=20))
            message=str(result.message)
        except BudgetReached:message='evaluation budget reached'
        selected=unpack(pack(grid));before=score(base,selected);after=before
        for alpha in (1.,.75,.5,.25):
            trial=np.clip(np.rint(grid+alpha*(best[1]-grid)),-64,63).astype(np.int8)
            trial=unpack(pack(trial));cost=score(base,trial)
            if cost['total']<after['total']-1e-9:selected,after=trial,cost
        # Task-aware integer moves use the very same mean-DE00 objective.
        variable=tools.tensor(selected).requires_grad_(True);loss(variable).backward()
        gradient=variable.grad.detach().cpu().numpy()
        nodes=np.argsort(np.linalg.norm(gradient,axis=1))[::-1][:settings['integer_node_budget']]
        trials=0;accepted=0
        for node in nodes:
            for channel in (None,0,1,2):
                trial=selected.astype(int).copy();direction=-np.sign(gradient[node]).astype(int)
                if channel is None:trial[node]+=direction
                else:trial[node,channel]+=direction[channel]
                trial=unpack(pack(np.clip(trial,-64,63).astype(np.int8)))
                cost=score(base,trial);trials+=1
                if cost['total']<after['total']-1e-9:selected,after=trial,cost;accepted+=1
        audit=dict(stage=label,calls=calls,before=before,after=after,solver_message=message,
            integer_trials=trials,integer_accepted=accepted,objective='mean DeltaE00 + small grid correction')
        events.append(audit);progress(**audit)
        return selected

    chosen=restored(resume['chosen'])if resume.get('chosen')else copy.deepcopy(min(
        [current,reference]if reference is not None else[current],key=lambda s:s['validation']))
    for index in range(settings['grid_rounds']):
        if index<grid_done:continue
        grid=optimize_grid(current['base'],current['grid'],'grid-'+str(index+1),settings['grid_evaluations'])
        current=dict(current,grid=grid,label='grid-'+str(index+1),validation=validation(current['base'],grid))
        if current['validation']<chosen['validation']:chosen=copy.deepcopy(current)
        save(output/'grid-progress.json',dict(round=index+1,validation=current['validation'],selected=chosen['label']))
        grid_done=index+1;persist(current,chosen)
        if index and 'prior_grid'in locals()and np.array_equal(grid,prior_grid):break
        prior_grid=grid.copy()
    grid_done=settings['grid_rounds']
    if chosen['validation']<current['validation']:current=copy.deepcopy(chosen)
    persist(current,chosen)
    for index in range(settings['rounds']):
        if index<joint_done:continue
        state=optimize_native(current['params'],current['grid'],'joint-native-'+str(index+1),settings['native_evaluations'])
        grid=optimize_grid(state['base'],state['grid'],'joint-grid-'+str(index+1),settings['grid_evaluations'])
        current=dict(state,grid=grid,label='joint-'+str(index+1),validation=validation(state['base'],grid))
        if current['validation']<chosen['validation']:chosen=copy.deepcopy(current)
        save(output/'joint-progress.json',dict(round=index+1,validation=current['validation'],selected=chosen['label']))
        joint_done=index+1;persist(current,chosen)
    prediction=model.predict_cpu(chosen['base'],chosen['grid'])
    def describe(base,grid,predicted=None):
        p=model.predict_cpu(base,grid)if predicted is None else predicted
        from perceptual import compare
        values={}
        for name in ('train','valid','test'):
            mask=split==name;distance=objective.distances(p[mask],target[mask])
            values[name]=dict(metrics(target[mask],p[mask]),delta_e00_mean=float(distance.mean()),
                delta_e00_p95=float(np.percentile(distance,95)),delta_e00_p99=float(np.percentile(distance,99)),delta_e00_max=float(distance.max()),
                display_uint8=compare(target[mask],p[mask]))
        correction=np.sqrt(np.mean(((p-base)*255)**2,axis=1))
        return dict(metrics=values,grid=dict(node_rms=float(np.sqrt(np.mean(grid.astype(float)**2))),
            node_max=int(np.abs(grid.astype(int)).max()),saturated_components=int(np.count_nonzero((grid==-64)|(grid==63))),
            mean_output_correction_rgb8=float(correction.mean()),p95_output_correction_rgb8=float(np.percentile(correction,95))))
    result_summary=describe(chosen['base'],chosen['grid'],prediction)
    report=dict(algorithm=request['algorithm'],execution_device=device,selected=chosen['label'],
        selected_validation=chosen['validation'],budget=dict(evaluations=evaluations,starts=starts),
        native_only=describe(chosen_native['base'],zero),result=result_summary,
        reference=describe(reference['base'],reference['grid'])if reference is not None else None,
        metrics=result_summary['metrics'],events=events,settings=settings,
        group_weights=profile['options']['group_weights'],sampling=profile['options']['search_options'],
        native_starts_resumed=resume.get('native_done',0),
        objective='mean continuous DeltaE00',gamma_shape='monotone; unrestricted curvature',
        gamma_admissibility=shape.audit_even(chosen['params']['gamma_y']),
        selection='validation mean DeltaE00 plus the same weak grid penalty; test never selects',camera_io=False,
        physical_color_accuracy_verified=False,historical_test_previously_observed=True)
    native=fields(chosen['params']);save(output/'parameters.json',native)
    (output/'grid.payload').write_bytes(pack(chosen['grid']))
    np.savez_compressed(output/'prediction.npz',prediction=prediction,target=target,baseline=chosen['base'],split=split)
    save(output/'complete.json',report)
    tracker.update(round=tracker.value['total_rounds'],stage='训练完成',state='done')
    return native,pack(chosen['grid']),report
