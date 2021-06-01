import os
from constructs import Construct
from aws_cdk.aws_s3_assets import Asset
from aws_cdk import (
    Stack, Duration, App, Environment, Tags,
    aws_ec2 as ec2,
    aws_route53 as _route53
)


dirname = os.path.dirname(__file__)


class RunAllAtOnce:
    def __init__(self):
        app = App()
        _env = Environment(region='eu-central-1')
        pattern = 'fra'
        ec2_stack = EC2FrpsStackCreate(app, f"frps-ec2-{pattern}", env=_env, pattern=pattern)
        eip_stack = EIPFrpsStackAttach(app, f"frps-eip-{pattern}", instance_id=ec2_stack.instance.instance_id,
                                       env=_env, pattern=pattern)
        Route53FrpsStack(app, id=f"Route53{pattern}FrpsStack", env=_env, pattern=pattern,
                         eip=eip_stack.eip.ref, private_ip=ec2_stack.instance.instance_private_ip)

        app.synth()


class EC2FrpsStackCreate(Stack):
    def __init__(self, scope: Construct, id: str, env, pattern, **kwargs) -> None:
        super().__init__(scope, id, env=env, **kwargs)
        self.instance = None

        vpc = ec2.Vpc.from_vpc_attributes(self, "VPC", vpc_id='vpc-abc123',
                                          availability_zones=['eu-central-1a'],
                                          public_subnet_ids=['subnet-xyz456'])

        vpc_sg = ec2.SecurityGroup.from_security_group_id(self, f'{pattern}-p1.vpc', 'sg-123456')


        # Root volume
        ebs_root_dev = ec2.EbsDeviceProps(delete_on_termination=True,
                                          volume_type=ec2.EbsDeviceVolumeType.GP2, volume_size=8)
        block_root_volume = ec2.BlockDeviceVolume(ebs_device=ebs_root_dev)
        block_root_device = ec2.BlockDevice(device_name='/dev/xvda', volume=block_root_volume)

        # Instance
        self.instance = ec2.Instance(self, f"{pattern}FrpsInstance",
                                     instance_type=ec2.InstanceType("t3a.nano"),
                                     machine_image=ec2.AmazonLinuxImage(
                                         generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
                                     ),
                                     vpc=vpc,
                                     security_group=vpc_sg,
                                     instance_name=f'{pattern}-frps',
                                     block_devices=[block_root_device],
                                     key_name='frps-key'
                                     )

        Tags.of(self.instance).add(key='Name', value=f'{pattern}-frps')
        Tags.of(self.instance).add(key='cfn.frps.stack', value='ec2-stack')

        # Script in S3 as Asset
        asset = Asset(self, "Asset", path=os.path.join(dirname, "setup.sh"))
        local_path = self.instance.user_data.add_s3_download_command(
            bucket=asset.bucket,
            bucket_key=asset.s3_object_key
        )

        # Userdata executes script from S3
        self.instance.user_data.add_execute_file_command(
            file_path=local_path
        )
        asset.grant_read(self.instance.role)


class EIPFrpsStackAttach(Stack):
    def __init__(self, scope: Construct, id: str, env, pattern, instance_id, **kwargs) -> None:
        super().__init__(scope, id, env=env, **kwargs)
        self.eip = None

        self.eip = ec2.CfnEIP(scope=self, id=f'FRPSEIP{pattern}', domain='vpc')
        ec2.CfnEIPAssociation(self, "EIPFRPSAttachment", instance_id=instance_id,
                              allocation_id=self.eip.attr_allocation_id)


class Route53FrpsStack(Stack):

    def __init__(self, scope: Construct, id: str, env, pattern, eip, private_ip, **kwargs) -> None:
        super().__init__(scope, id, env=env, **kwargs)

        vc_io_hosted_zone = 'ZONEID'
        hz = _route53.HostedZone.from_hosted_zone_attributes(
            self, id=f"Frps{pattern}HostedZone", hosted_zone_id=vc_io_hosted_zone, zone_name='cloudopz.co')

        record = f'{pattern}-frps'
        _route53.ARecord(
            scope=self, id=f'frps{pattern}Record', target=_route53.RecordTarget.from_ip_addresses(eip),
            zone=hz, record_name=record, ttl=Duration.seconds(60)
        )

        """ Create frps record on fra-vc-p1.zone zone """
        vc_p_zone = 'ZVPCZONEID'
        vc_p_hz = _route53.HostedZone.from_hosted_zone_attributes(
            self, id=f"Frps{pattern}VCPHostedZone", hosted_zone_id=vc_p_zone, zone_name='cloudopz.zone'
        )
        frps_record = 'frps'
        _route53.ARecord(
            scope=self, id=f'frps{pattern}VCPRecord', target=_route53.RecordTarget.from_ip_addresses(private_ip),
            zone=vc_p_hz, record_name=frps_record, ttl=Duration.seconds(60)
        )
