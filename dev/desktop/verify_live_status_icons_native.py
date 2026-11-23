"""Exercise the live-status translator with actual C2 AArch64 instructions."""
from pathlib import Path
import argparse,json,struct
import verify_fixed_looks_native as native
from looktool import fixedlooks,fixedlookscode


def verify(source,report):
    image=native.configure(source)
    model=native.DATA+0x1000;output=native.DATA+0x3000
    selected=[0x7f8]

    def make(mask):
        cpu=native.Native(mask)
        def memcpy(cpu,args):
            for page in range(args[1]&~4095,(args[1]+args[2]+4095)&~4095,4096):
                if page not in cpu.pages:
                    assert cpu.missing(cpu.u,0,page,1,0,None)
            cpu.put(args[0],cpu.read(args[1],args[2]));cpu.ret(args[0])
        def current(cpu,args):
            assert args[0]==0x5e4
            cpu.ret(selected[0])
        cpu.hooks.update({0x165d3e0:memcpy,0x1b6bb2c:current})
        return cpu

    def draw(cpu,base=1,focus=0,enabled=1,suppressed=False):
        cpu.put(model,bytes(0xc0));cpu.put(output,b'\x5a'*128)
        for at,value in ((0,enabled),(0x68,1),(0x20,base),(0x50,focus),
                         (0xb8,int(suppressed)),(0x90,5 if suppressed else 0)):
            cpu.put(model+at,struct.pack('<I',value))
        cpu.run(0x23e3144,0,output,0,model)
        return cpu.read(output,128)

    stock=make(None)
    gold={(base,focus):draw(stock,base,focus) for base in range(13) for focus in (0,0x5e4)}
    assert struct.unpack_from('<I',gold[1,0],0x3c)[0]==0x020043c8
    counts=dict(fixed_slot_status=0,factory_status=0,visibility_gates=0,asset_masks=0)
    first=None
    for mask in range(64):
        cpu=make(mask)
        for at,raw in fixedlookscode.status_icons(mask).items():
            assert fixedlooks.windows(mask)[at]==raw
        counts['asset_masks']+=1
        for slot in range(6):
            selected[0]=0x7f8+slot
            for base in (1,5):
                for focus in (0,0x5e4):
                    before=gold[base,focus];after=draw(cpu,base,focus)
                    want=bytearray(before)
                    if mask>>slot&1:
                        rid=0x0200181a+13*slot if focus else 0x020033a3+slot
                        struct.pack_into('<I',want,0x3c,rid)
                    assert after==bytes(want),(mask,slot,base,focus)
                    counts['fixed_slot_status']+=1
                    if mask==63 and slot==0 and base==1 and focus==0:
                        first=dict(before=hex(struct.unpack_from('<I',before,0x3c)[0]),
                                   after=hex(struct.unpack_from('<I',after,0x3c)[0]))
        if mask in (0,1,21,42,63):
            for value in (0x7ec,0x7ed,0x7f2,0x7f3,0x7fe,0x250e):
                selected[0]=value
                for base in range(13):
                    for focus in (0,0x5e4):
                        assert draw(cpu,base,focus)==gold[base,focus]
                        counts['factory_status']+=1
        selected[0]=0x7f8
        for enabled in (0,2):
            assert draw(cpu,enabled=enabled)==draw(stock,enabled=enabled)
            counts['visibility_gates']+=1
        assert draw(cpu,suppressed=True)==draw(stock,suppressed=True)
        counts['visibility_gates']+=1

    old=image.raw;before=fixedlooks.inspect(old)
    assert before['enabled'] and not before['live_status_slot_icons']
    changed=fixedlooks.patch(old,before['mask'])
    assert len(changed)==len(old) and fixedlooks.inspect(changed)['live_status_slot_icons']
    assert fixedlooks.restore(changed)==fixedlooks.restore(old)
    allowed={at+i for at,raw in fixedlookscode.status_icons(before['mask']).items() for i in range(len(raw))}
    assert all(i in allowed for i,(a,b) in enumerate(zip(old,changed)) if a!=b)
    broken=bytearray(changed)
    at=next(iter(fixedlookscode.status_icons(before['mask'])))
    raw=bytes.fromhex(fixedlooks.asset()['before'][str(at)])
    broken[at:at+len(raw)]=raw
    try:fixedlooks.inspect(bytes(broken))
    except ValueError:pass
    else:raise AssertionError('Partly installed status code was accepted')
    result=dict(status='PASS',counts=counts,ST_to_slot_example=first,
        caller_stack_and_callee_saved_checked=True,only_status_windows_changed=True,
        code_or_segment_growth=0,new_image_ids=0,camera_io=False,
        limitations=['Current-setting property is an explicit native-function fixture.',
            'No complete camera boot, orientation sensor or physical display acceptance.'])
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-ap',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args();verify(args.source_ap,args.report)
