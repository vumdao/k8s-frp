<p align="center">
  <a href="https://dev.to/vumdao">
    <img alt="FRP - Fast Reserve Proxy - Connect To Database In Private Network" src="https://github.com/vumdao/k8s-frp/blob/master/img/cover.jpg?raw=true" width="700" />
  </a>
</p>
<h1 align="center">
  <div><b>FRP - Fast Reserve Proxy - Connect To Database In Private Network</b></div>
</h1>

### **Open connection to database servers such as postgresql, redis, mongodb, etc. within officie network**

---

## What’s In This Document
- [What is FRP?](#-What-is-FRP?)
- [Create FPR Server Using AWS CDK 2.0](#-Create-FPR-Server-Using-AWS-CDK-2.0)
- [Set up connection to Database In Private Network](#-Set-up-connection-to-Database-In-Private-Network)
- [Conclusion](#-Conclusion)

---

### 🚀 **[What is FRP?](#-What-is-FRP?)**
[frp](https://github.com/fatedier/frp) is a fast reverse proxy to help you expose a local server behind a NAT or firewall to the Internet. As of now, it supports TCP and UDP, as well as HTTP and HTTPS protocols, where requests can be forwarded to internal services by domain name.

![Alt-Text](https://github.com/vumdao/k8s-frp/blob/master/img/frp.png?raw=true)

### 🚀 **[Create FPR Server Using AWS CDK 2.0](#-Create-FPR-Server-Using-AWS-CDK-2.0)**
- Using CDK will help to spread of the infra to multiple regions
- The stack includes:
    - Create EC2 instance (type t3a.nano) and then run `setup.sh` script to start fprs systemD service
    - Allocation EIP to the EC2 instance
    - Create record set `frps.cloudopz.co` point to the EIP
    - Create record set of `frps` in VPC private zone

```
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
```

### 🚀 **[Set up connection to Database In Private Network](#-Set-up-connection-to-Database-In-Private-Network)**
<br/>

![Alt-Text](https://github.com/vumdao/k8s-frp/blob/master/img/flow.png?raw=true)

1. `frps.cloudopz.co` is record set point to public IP of the frp server (An EC2 instance), security group of the EC2 should allow only ports within office network or VPN

2. FRP server uses private network in order to talk with FRP client which is a k8s service and contains protocol methods, as well as binding port to connect to databases

3. Structure of project:
```
⚡ $ tree
.
├── Dockerfile
├── start.sh
└── frpc.ini
```

4. Build image and then push to ECR `cloudopz/frpc:latest`

5. Deploy FRP client in k8s as a statefulset service
```
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: frpc
spec:
  serviceName: "frpc"
  replicas: 1
  selector:
    matchLabels:
      ss: frpc
  template:
    metadata:
      labels:
        ss: frpc
    spec:
      containers:
      - name: frpc
        image: cloudopz/frpc:latest
      restartPolicy: Always
```

### 🚀 **Monitor FRP using dashboard at port 7500**
<br/>

![Alt-Text](https://github.com/vumdao/k8s-frp/blob/master/img/dashboard.png?raw=true)

### 🚀 **[Conclusion](#-Conclusion)**
- There are many ways to provide connection to database, please share what you experienced
- Providing connection to database for developer shoud restrict permission by granting proper permission on specific database/schema only

---


<h3 align="center">
  <a href="https://dev.to/vumdao">:stars: Blog</a>
  <span> · </span>
  <a href="https://github.com/vumdao/k8s-frp">Github</a>
  <span> · </span>
  <a href="https://stackoverflow.com/users/11430272/vumdao">stackoverflow</a>
  <span> · </span>
  <a href="https://www.linkedin.com/in/vu-dao-9280ab43/">Linkedin</a>
  <span> · </span>
  <a href="https://www.linkedin.com/groups/12488649/">Group</a>
  <span> · </span>
  <a href="https://www.facebook.com/CloudOpz-104917804863956">Page</a>
  <span> · </span>
  <a href="https://twitter.com/VuDao81124667">Twitter :stars:</a>
</h3>
