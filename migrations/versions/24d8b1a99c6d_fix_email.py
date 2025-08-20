"""fix email

Revision ID: 24d8b1a99c6d
Revises: be07f4772d09
Create Date: 2025-08-20 16:01:31.698661

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24d8b1a99c6d'
down_revision = 'be07f4772d09'
branch_labels = None
depends_on = None


def upgrade():
    # ### create new tables ###
    op.create_table(
        'achievement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(length=100), nullable=True),
        sa.Column('points', sa.Integer(), nullable=True),
        sa.Column('condition', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'conversation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('is_group', sa.Boolean(), nullable=True),
        sa.Column('group_name', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id']),
        sa.ForeignKeyConstraint(['sender_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notification_type', sa.String(length=20), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('related_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'user_achievement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('achievement_id', sa.Integer(), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievement.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'user_conversations',
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'])
    )

    # ### alter post table ###
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hashtags', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('like_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('comment_count', sa.Integer(), nullable=True))

    # ### alter user table ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=False))  # Düzeltilmiş
        batch_op.add_column(sa.Column('points', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('level', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('experience', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_activity', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('two_factor_enabled', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('two_factor_secret', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('login_attempts', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_login_attempt', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_user_email', ['email'])  # Unique constraint ismi eklendi

def downgrade():
    # ### revert user table ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_email', type_='unique')
        batch_op.drop_column('last_login_attempt')
        batch_op.drop_column('login_attempts')
        batch_op.drop_column('two_factor_secret')
        batch_op.drop_column('two_factor_enabled')
        batch_op.drop_column('is_verified')
        batch_op.drop_column('last_activity')
        batch_op.drop_column('experience')
        batch_op.drop_column('level')
        batch_op.drop_column('points')
        batch_op.drop_column('email')

    # ### revert post table ###
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.drop_column('comment_count')
        batch_op.drop_column('like_count')
        batch_op.drop_column('hashtags')

    # ### drop new tables ###
    op.drop_table('user_conversations')
    op.drop_table('user_achievement')
    op.drop_table('notification')
    op.drop_table('message')
    op.drop_table('conversation')
    op.drop_table('achievement')
