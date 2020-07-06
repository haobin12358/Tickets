import uuid

from flask import request, current_app
from sqlalchemy import true, false

from tickets.extensions.error_response import ParamsError
from tickets.extensions.interface.user_interface import is_admin, admin_required
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.models import Admin
from tickets.models.index import MiniProgramBanner, LinkContent


class CIndex:
    LCBASE = '/pages/personal/richText?lcid={}'

    def list_mp_banner(self):
        """小程序轮播图获取"""
        filter_args = []
        if not is_admin():
            filter_args.append(MiniProgramBanner.MPBshow == true())
        mpbs = MiniProgramBanner.query.filter(MiniProgramBanner.isdelete == false(),
                                              *filter_args
                                              ).order_by(MiniProgramBanner.MPBsort.asc(),
                                                         MiniProgramBanner.createtime.desc()).all()
        [x.hide('ADid') for x in mpbs]
        return Success(data=mpbs)

    @admin_required
    def set_mp_banner(self):
        """小程序轮播图"""
        data = parameter_required(('mpbpicture',))
        mpbid = data.get('mpbid')
        mpb_dict = {'MPBpicture': data.get('mpbpicture'),
                    'MPBsort': data.get('mpbsort'),
                    'MPBshow': data.get('mpbshow'),
                    'contentlink': data.get('contentlink')}
        with db.auto_commit():
            if not mpbid:
                mpb_dict['MPBid'] = str(uuid.uuid1())
                mpb_dict['ADid'] = getattr(request, 'user').id
                mpb_instance = MiniProgramBanner.create(mpb_dict)
                # BASEADMIN().create_action(AdminActionS.insert.value, 'MiniProgramBanner', mpb_instance.MPBid)
                msg = '添加成功'
            else:
                mpb_instance = MiniProgramBanner.query.filter_by_(MPBid=mpbid).first_('未找到该轮播图信息')
                if data.get('delete'):
                    mpb_instance.update({'isdelete': True})
                    # BASEADMIN().create_action(AdminActionS.delete.value, 'MiniProgramBanner', mpb_instance.MPBid)
                    msg = '删除成功'
                else:
                    mpb_instance.update(mpb_dict, null='not')
                    # BASEADMIN().create_action(AdminActionS.update.value, 'MiniProgramBanner', mpb_instance.MPBid)
                    msg = '编辑成功'
            db.session.add(mpb_instance)
        return Success(message=msg, data={'mpbid': mpb_instance.MPBid})

    @admin_required
    def set_linkcontent(self):
        body = request.json
        admin = Admin.query.filter(Admin.isdelete == false(), Admin.ADid == getattr(request, 'user').id).first()
        current_app.logger.info('当前管理员是 {}'.format(admin.ADname))
        lcid = body.get('lcid')
        lccontent = body.get('lccontent')
        with db.auto_commit():
            if lcid:
                lc = LinkContent.query.filter(LinkContent.LCid == lcid, LinkContent.isdelete == False).first()
                if body.get('delete'):
                    current_app.logger.info('开始删除富文本内容 lcid = {}'.format(lcid))
                    if not lc:
                        raise ParamsError('该内容已删除')
                    lc.isdelete = True
                    return Success('删除成功', data=lcid)
                if lc:
                    current_app.logger.info('开始更新富文本内容 lcid = {}'.format(lcid))
                    if lccontent:
                        lc.LCcontent = lccontent
                    db.session.add(lc)
                    return Success('更新成功', data=lcid)

            if not lccontent:
                raise ParamsError('富文本内容不能为空')
            lc = LinkContent.create({
                'LCid': str(uuid.uuid1()),
                'LCcontent': lccontent
            })
            current_app.logger.info('开始创建富文本内容 lcid = {}'.format(lc.LCid))
            db.session.add(lc)
            return Success('添加成功', data=lc.LCid)

    def get_linkcontent(self):
        data = parameter_required('lcid')
        lcid = data.get('lcid')
        lc = LinkContent.query.filter_by(LCid=lcid, isdelete=False).first()
        if not lc:
            raise ParamsError('链接失效')
        return Success(data=lc)

    @admin_required
    def list_linkcontent(self):
        lc_list = LinkContent.query.filter(LinkContent.isdelete == False).order_by(
            LinkContent.createtime.desc()).all_with_page()
        for lc in lc_list:
            self._fill_lc(lc)
        return Success(data=lc_list)

    def _fill_lc(self, lc):
        lc.fill('lclink', self.LCBASE.format(lc.LCid))
